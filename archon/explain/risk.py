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


@lru_cache(maxsize=1)
def _load_yaml() -> tuple[Mapping[str, int], Mapping[str, str | None]]:
    """Load and validate risk_rules.yaml. Loud on any misconfiguration."""
    data = yaml.safe_load(_RULES_FILE.read_text(encoding="utf-8"))
    rules: dict[str, int] = dict(data["rules"])
    flags: dict[str, str | None] = dict(data["pattern_flags"])
    for key, value in rules.items():
        if not isinstance(value, int):
            raise TypeError(f"risk rule {key!r} must be an int, got {value!r}")
    return rules, flags


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
    assert record.evidence is not None  # matched records always carry evidence
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
    """Score one record. Pure: same input, same output, always."""
    if rules is not None:
        base = _load_yaml()
        merged = {**base[0], **dict(rules)}
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
    """_record_flags against an explicit rules mapping (test override)."""
    if record.status == "unverified":
        return [("UNVERIFIED_FORMULA", rules["UNVERIFIED_FORMULA"])]
    assert record.evidence is not None
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
