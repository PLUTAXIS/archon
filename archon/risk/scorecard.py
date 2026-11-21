"""Workbook risk scorecard: one 0-100 score with a reason for every point.

Weights and points live in scorecard.yaml (data, not code). Pure and
deterministic: the same signal counts always give the same scorecard.

    card = score_workbook({"override_bug": 2, "cycle": 1, ...})
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CAP = 100
_FILE = Path(__file__).parent / "scorecard.yaml"


@lru_cache(maxsize=1)
def load_scorecard() -> dict[str, Any]:
    """Load and validate scorecard.yaml once."""
    data = yaml.safe_load(_FILE.read_text(encoding="utf-8"))
    total = sum(axis["weight"] for axis in data["axes"].values())
    if total != 100:
        raise ValueError(f"axis weights must sum to 100, got {total}")
    names = [s for axis in data["axes"].values() for s in axis["signals"]]
    if len(names) != len(set(names)):
        raise ValueError("a signal may belong to only one axis")
    return data


def signals() -> list[str]:
    """Every signal name the scorecard expects, in file order."""
    return [s for axis in load_scorecard()["axes"].values() for s in axis["signals"]]


def score_workbook(counts: Mapping[str, int]) -> dict[str, Any]:
    """Score a workbook from its signal counts. Unknown or missing signals raise."""
    expected = set(signals())
    if set(counts) != expected:
        raise ValueError(
            f"signal mismatch: missing {sorted(expected - set(counts))}, "
            f"unknown {sorted(set(counts) - expected)}"
        )
    data = load_scorecard()
    axes = []
    weighted = 0.0
    for axis_id, axis in data["axes"].items():
        contributions = [
            {"signal": name, "label": spec["label"], "count": counts[name],
             "points": counts[name] * spec["points"]}
            for name, spec in axis["signals"].items()
            if counts[name]
        ]
        raw = sum(c["points"] for c in contributions)
        score = min(raw, _CAP)
        weighted += axis["weight"] * score / 100
        axes.append({"id": axis_id, "title": axis["title"], "weight": axis["weight"],
                     "score": score, "capped": raw > _CAP, "contributions": contributions})
    total = int(weighted + 0.5)  # round half up, not to even
    band = next(b["label"] for b in data["bands"] if total >= b["min"])
    return {"score": total, "band": band, "axes": axes}
