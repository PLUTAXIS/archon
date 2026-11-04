from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from archon.formula.r1c1 import num_to_col, parse_address, to_r1c1

Row = tuple[str, str, str]
ClusterKey = tuple[str, str, str]
Clusters = dict[ClusterKey, list[tuple[int, str]]]
Constant = tuple[str, str, str]


def cluster_cells(rows: Iterable[Row]) -> tuple[Clusters, list[Constant]]:
    clusters: defaultdict[ClusterKey, list[tuple[int, str]]] = defaultdict(list)
    constants: list[Constant] = []
    for sheet, addr, content in rows:
        text = str(content).strip()
        if not text:
            continue
        row, col = parse_address(addr)
        if text.startswith("="):
            key = (sheet, num_to_col(col), to_r1c1(text, addr))
            clusters[key].append((row, addr))
        else:
            constants.append((sheet, addr, text))
    for members in clusters.values():
        members.sort()
    return dict(clusters), constants


def summarise(clusters: Clusters, constants: list[Constant]) -> dict[str, Any]:
    formula_cells = sum(len(m) for m in clusters.values())
    n = len(clusters)
    return {
        "formula_cells": formula_cells,
        "clusters": n,
        "constant_cells": len(constants),
        "compression_ratio": formula_cells / n if n else 0.0,
    }


def contiguous_runs(rows_sorted: list[int]) -> list[tuple[int, int]]:
    if not rows_sorted:
        return []
    runs: list[tuple[int, int]] = []
    start = prev = rows_sorted[0]
    for r in rows_sorted[1:]:
        if r != prev + 1:
            runs.append((start, prev))
            start = r
        prev = r
    runs.append((start, prev))
    return runs


def load_formulas(path: str | Path) -> list[Row]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(d["sheet"], d["cell_reference"], d["formula"]) for d in data]
