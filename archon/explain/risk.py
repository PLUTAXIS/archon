"""Risk scoring: pure function from ExplanationRecord to a printable score.

Rules live in risk_rules.yaml (data, not code). Deterministic: sorted,
set-free, timestamp-free. Known limitation (accepted, option A): only the
outermost idiom is scored; a volatile/approx-lookup call nested inside
IFERROR is invisible to a record-only scorer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from yaml.resolver import BaseResolver

from archon.contracts.explain import ExplanationRecord
from archon.contracts.graph import Risk

_SCORE_CAP = 100
_RULES_FILE = Path(__file__).parent / "risk_rules.yaml"


@dataclass(frozen=True)
class RiskComponent:
    """A single named contribution to the risk score."""

    flag: str
    points: int


@dataclass(frozen=True)
class RiskResult:
    """Score plus its printable, sorted breakdown."""

    score: int
    flags: tuple[str, ...]
    components: tuple[RiskComponent, ...]


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently keeping the last."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    """Build a mapping node, raising ValueError on any duplicate key."""
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key {key!r} in YAML mapping")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _validate_weight(key: str, value: object) -> int:
    """Validate one weight: int (not bool), non-negative. Return it."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"risk rule {key!r} must be an int, got {value!r}")
    if value < 0:
        raise ValueError(f"risk rule {key!r} must be >= 0, got {value}")
    return value


def _parse_rules(text: str) -> tuple[dict[str, int], dict[str, str | None]]:
    """Parse and validate rules YAML text. Loud on any misconfiguration."""
    data = yaml.load(text, Loader=_StrictLoader)
    rules = {key: _validate_weight(key, value) for key, value in data["rules"].items()}
    flags: dict[str, str | None] = dict(data["pattern_flags"])
    return rules, flags


@lru_cache(maxsize=1)
def _load_yaml() -> tuple[Mapping[str, int], Mapping[str, str | None]]:
    """Load and validate risk_rules.yaml once; cached for the process."""
    return _parse_rules(_RULES_FILE.read_text(encoding="utf-8"))


def load_rules() -> dict[str, int]:
    """Return the flag-to-points mapping."""
    return dict(_load_yaml()[0])


def pattern_flags() -> dict[str, str | None]:
    """Return the pattern-id-to-flag mapping (null = explicit zero risk)."""
    return dict(_load_yaml()[1])


def _record_flags(record: ExplanationRecord) -> list[tuple[str, int]]:
    """Derive (flag, points) pairs from one record. Never guesses."""
    rules = load_rules()
    pairs: list[tuple[str, int]] = []
    if record.status == "unverified":
        pairs.append(("UNVERIFIED_FORMULA", rules["UNVERIFIED_FORMULA"]))
        return pairs
    if record.evidence is None:
        raise ValueError("matched record must carry evidence (pattern_id required)")
    flag = pattern_flags().get(record.evidence.pattern_id, "")
    if flag is None:
        return pairs  # explicit zero-risk decision for this pattern
    if flag not in rules:
        raise ValueError(f"no points defined for flag {flag!r}")
    if flag == "NESTED_IF_DEPTH":
        assert record.idiom == "tiered_rate_table"
        assert record.evidence.captured_vars["bracket_count"].isdigit()
        levels = int(record.evidence.captured_vars["bracket_count"]) - 1
        pairs.append((f"NESTED_IF_DEPTH_{levels}", rules[flag] * levels))
    else:
        pairs.append((flag, rules[flag]))
    return pairs


def score_record(
    record: ExplanationRecord,
    *,
    rules: Mapping[str, int] | None = None,
) -> RiskResult:
    """Score one record. Pure: same input, same output, always.

    `rules` overrides YAML weights per flag for this call only, validated
    with the same strictness as the file: int, non-bool, non-negative.
    """
    if rules is not None:
        validated = {key: _validate_weight(key, value) for key, value in rules.items()}
        merged = {**_load_yaml()[0], **validated}
        pairs = _record_flags_with(record, merged)
    else:
        pairs = _record_flags(record)
    components = tuple(sorted(RiskComponent(f, p) for f, p in pairs))
    flags = tuple(sorted({c.flag for c in components}))
    score = min(sum(c.points for c in components), _SCORE_CAP)
    return RiskResult(score=score, flags=flags, components=components)


def _record_flags_with(
    record: ExplanationRecord, rules: Mapping[str, int]
) -> list[tuple[str, int]]:
    """Derive (flag, points) pairs against an explicit rules mapping."""
    if record.status == "unverified":
        return [("UNVERIFIED_FORMULA", rules["UNVERIFIED_FORMULA"])]
    if record.evidence is None:
        raise ValueError("matched record must carry evidence (pattern_id required)")
    flag = pattern_flags().get(record.evidence.pattern_id, "")
    if flag is None:
        return []
    if flag not in rules:
        raise ValueError(f"no points defined for flag {flag!r}")
    if flag == "NESTED_IF_DEPTH":
        levels = int(record.evidence.captured_vars["bracket_count"]) - 1
        return [(f"NESTED_IF_DEPTH_{levels}", rules[flag] * levels)]
    return [(flag, rules[flag])]


def format_components(result: RiskResult) -> str:
    """Render the printable breakdown. Deterministic exact text."""
    return ", ".join(f"{c.flag}: +{c.points}" for c in result.components)


def to_contract_risk(result: RiskResult) -> Risk:
    """Adapt a RiskResult to the Contract B Risk model."""
    return Risk(score=result.score, flags=list(result.flags))
