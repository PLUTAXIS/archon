"""Parse-failure KPI tracking.

Every formula archon encounters is counted. Failures are never
silently dropped — they route to the unverified appendix.
KPI target (SCOPE.md): parse_failure_rate < 5%.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseKPI:
    source: str = "default"
    total: int = 0
    parsed: int = 0
    failed: int = 0
    failure_reasons: Counter = field(default_factory=Counter)
    failures: list = field(default_factory=list)

    def record_parsed(self, ref: str) -> None:
        self.total += 1
        self.parsed += 1

    def record_failed(self, ref: str, formula: str, reason: str) -> None:
        self.total += 1
        self.failed += 1
        self.failure_reasons[reason] += 1
        self.failures.append({
            "ref": ref,
            "formula": formula[:200],
            "reason": reason,
        })

    @property
    def failure_rate(self) -> float:
        return self.failed / self.total if self.total else 0.0

    @property
    def meets_target(self) -> bool:
        return self.failure_rate < 0.05

    def summary(self) -> dict:
        return {
            "kpi": "parse_failure_rate",
            "source": self.source,
            "total_formulas": self.total,
            "parsed": self.parsed,
            "failed": self.failed,
            "failure_rate": round(self.failure_rate, 4),
            "target": "< 0.05",
            "meets_target": self.meets_target,
            "failure_reasons": dict(self.failure_reasons.most_common()),
        }

    def write(self, path) -> None:
        Path(path).write_text(
            json.dumps(self.summary(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
