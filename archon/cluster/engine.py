"""Formula clustering: group cells that share the same relative (R1C1) formula.

Input rows are (sheet, address, content) where content is either a formula
("=B2*C2") or a hardcoded value ("145000").

    clusters, constants = cluster_cells(rows)
    summarise(clusters, constants)["compression_ratio"]
"""

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
    """Group formula cells by (sheet, column, R1C1 text) and separate out constants.

    `rows` is an iterable of (sheet, address, content) tuples, where content is
    either a formula string starting with "=" or a hardcoded value. Blank
    content is skipped. Returns (clusters, constants), where clusters maps
    each (sheet, column, R1C1 text) key to its sorted list of (row, address)
    members, and constants lists every non-formula cell found.
    """
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
    """Summarise clustering results: total formula cells, cluster count,
    constant count, and the resulting compression ratio (cells per cluster).
    """
    formula_cells = sum(len(m) for m in clusters.values())
    n = len(clusters)
    return {
        "formula_cells": formula_cells,
        "clusters": n,
        "constant_cells": len(constants),
        "compression_ratio": formula_cells / n if n else 0.0,
    }


def contiguous_runs(rows_sorted: list[int]) -> list[tuple[int, int]]:
    """Collapse a sorted list of row numbers into (start, end) runs.

    Example: [2, 3, 4, 6, 7] -> [(2, 4), (6, 7)]. A gap inside a cluster's
    row range usually indicates a hardcoded override sitting in the middle
    of an otherwise-dragged formula column.
    """
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
    """Load formula rows from Saba's extracted_formulas.json format.

    Expects a JSON array of objects with "sheet", "cell_reference", and
    "formula" keys, and returns them as (sheet, address, content) tuples.
    A null "formula" (used by some extractors for blank cells) is treated
    as an empty string rather than the literal text "None". Raises
    ValueError, naming the bad entry's index, if the file is not a JSON
    array or an entry is missing a required field.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected a JSON array of formula records")
    rows: list[Row] = []
    for i, d in enumerate(data):
        try:
            content = d["formula"]
            rows.append((d["sheet"], d["cell_reference"], "" if content is None else content))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Bad formula record at index {i}: {d!r}") from exc
    return rows
