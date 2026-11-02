"""Deterministic risk score: every point is attributed to a named flag."""

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from archon.contracts.explain import ExplanationRecord
from archon.contracts.graph import Risk

MAX_SCORE = 100
_RULES_FILE = Path(__file__).parent / "risk_rules.yaml"


@dataclass(frozen=True)
class RiskComponent:
    flag: str
    points: int


@dataclass(frozen=True)
class RiskResult:
    score: int
    flags: tuple[str, ...]
    components: tuple[RiskComponent, ...]


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    with _RULES_FILE.open(encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle)
    return data


def explicit_rule_ids() -> tuple[str, ...]:
    return tuple(sorted(_load()["rules"]))


def build_result(components: Iterable[RiskComponent]) -> RiskResult:
    unique = sorted(
        set(components), key=lambda c: (c.flag, c.points)
    )
    flags = tuple(sorted({c.flag for c in unique}))
    total = sum(c.points for c in unique)
    return RiskResult(
        score=min(total, MAX_SCORE),
        flags=flags,
        components=tuple(unique),
    )


def score_record(record: ExplanationRecord) -> RiskResult:
    data = _load()
    if record.status == "unverified":
        rule = data["unverified"]
        return build_result([RiskComponent(rule["flag"], rule["points"])])

    if record.evidence is None or record.evidence.pattern_id is None:
        raise ValueError("matched record without pattern_id cannot be scored")
    pattern_id = record.evidence.pattern_id
    rule = data["rules"][pattern_id]  # KeyError on purpose: no silent zero

    if "points_per_level" in rule:
        levels = int(record.evidence.captured_vars["bracket_count"]) - 1
        flag = f"{rule['flag']}_{levels}"
        return build_result(
            [RiskComponent(flag, rule["points_per_level"] * levels)]
        )
    if rule["points"] == 0:
        return build_result([])
    return build_result([RiskComponent(rule["flag"], rule["points"])])


def format_components(result: RiskResult) -> str:
    lines = [f"{c.flag} +{c.points}" for c in result.components]
    lines.append(f"TOTAL {result.score}")
    return "\n".join(lines)


def to_contract_risk(result: RiskResult) -> Risk:
    return Risk(score=result.score, flags=list(result.flags))
