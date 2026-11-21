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

import blake3

from archon.formula.ast import BinOp, Func, Lit, Node, Ref, UnaryOp
from archon.formula.parser import ParseError, parse
from archon.formula.r1c1 import num_to_col, parse_address, to_r1c1, to_r1c1_ast
from archon.parser.kpi import ParseKPI

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


# --- AST-hash-based clustering ---------------------------------------------
#
# cluster_cells() above clusters by string equality of R1C1 text (the
# original, pre-parser shortcut). The function below is the brief's real
# architecture (see Project Archon brief §3): cluster by blake3 hash of the
# formula's *canonical AST* -- the parsed, R1C1-translated tree -- rather
# than its text. This means two formulas that are structurally identical
# but spelled differently (e.g. differing only in incidental whitespace
# the tokenizer already discards) are guaranteed to land in the same
# cluster. Note this does NOT currently cover function-name case (SUM vs
# sum): the parser preserves a function's original case in Func.name, so
# sum(A1) and SUM(A1) hash differently today. The real payoff is
# robustness: this is the path any future formula-text normalization (e.g.
# adding case-insensitive function names in the parser or here) rides
# on for free, since it hashes structure, not text.
#
# This also finally confirms the cluster-id format Mainak's PROGRESS.md
# flagged as "to confirm with Senpai": a cluster's id is the hex blake3
# digest of its canonical AST string, computed by _canonical_ast_string().


def _canonical_ast_string(node: Node) -> str:
    """Serialize an AST node into a deterministic string for hashing.

    Written by hand, rather than relying on the dataclasses' own repr(),
    so the cluster-id format doesn't silently change if ast.py's repr
    output ever changes for unrelated reasons (e.g. a field reorder).
    """
    if isinstance(node, Lit):
        return f"L:{node.value!r}"
    if isinstance(node, Ref):
        return f"R:{node.sheet!r}:{node.r1c1}:{node.absolute}"
    if isinstance(node, UnaryOp):
        return f"U:{node.op}:{node.postfix}:({_canonical_ast_string(node.operand)})"
    if isinstance(node, BinOp):
        return (
            f"B:{node.op}:({_canonical_ast_string(node.left)},"
            f"{_canonical_ast_string(node.right)})"
        )
    if isinstance(node, Func):
        args = ",".join(_canonical_ast_string(a) for a in node.args)
        return f"F:{node.name}:[{args}]"
    raise TypeError(f"Unknown AST node type: {type(node).__name__}")


def cluster_id_for(formula: str, addr: str) -> str:
    """Compute the blake3-hex cluster id for one formula at one address.

    Parses the formula, translates every Ref to real R1C1 text anchored at
    addr, serializes the result canonically, and hashes it. Raises
    ParseError if the formula can't be parsed, or ValueError if its AST is
    nested too deeply to translate (see parser.parse and r1c1.to_r1c1_ast).
    """
    row, col = parse_address(addr)
    ast = parse(formula)
    canonical_ast = to_r1c1_ast(ast, (row, col))
    return blake3.blake3(_canonical_ast_string(canonical_ast).encode("utf-8")).hexdigest()


def _memo_cluster_id(memo: dict[str, str | ValueError], formula: str, addr: str) -> str:
    """cluster_id_for(), computed once per distinct R1C1 text."""
    try:
        key = to_r1c1(formula, addr)
    except ValueError:
        return cluster_id_for(formula, addr)  # can't key it: compute directly
    if key not in memo:
        try:
            memo[key] = cluster_id_for(formula, addr)
        except ValueError as exc:  # ParseError is a ValueError
            memo[key] = exc
    found = memo[key]
    if isinstance(found, ValueError):
        raise found
    return found


def cluster_cells_ast(
    rows: Iterable[Row],
    kpi: ParseKPI | None = None,
) -> tuple[Clusters, list[Constant], list[Constant]]:
    """Group formula cells by (sheet, column, blake3 AST-hash) and separate
    out constants -- the AST-hash-based counterpart to cluster_cells().

    Returns (clusters, constants, unparsed). clusters and constants have
    the same shapes as cluster_cells()'s return value. unparsed lists any
    formula cell that could not be parsed or translated (a malformed or
    unsupported formula) as (sheet, address, content) tuples, rather than
    raising and aborting the whole batch -- these need a human or Saba's
    ground truth, not a silent drop and not a crash.
    """
    clusters: defaultdict[ClusterKey, list[tuple[int, str]]] = defaultdict(list)
    constants: list[Constant] = []
    unparsed: list[Constant] = []
    # Copied formulas share one relative (R1C1) text, and the AST-hash id
    # depends only on it, so each distinct relative formula is parsed once
    # (500,000 dragged cells -> a few hundred parses). Failures are memoised too.
    memo: dict[str, str | ValueError] = {}
    for sheet, addr, content in rows:
        text = str(content).strip()
        if not text:
            continue
        if not text.startswith("="):
            constants.append((sheet, addr, text))
            continue
        try:
            row, col = parse_address(addr)
            cid = _memo_cluster_id(memo, text, addr)
        except (ParseError, ValueError) as exc:
            unparsed.append((sheet, addr, text))
            if kpi is not None:
                kpi.record_failed(addr, text, str(exc))
            continue
        if kpi is not None:
            kpi.record_parsed(addr)
        key = (sheet, num_to_col(col), cid)
        clusters[key].append((row, addr))
    for members in clusters.values():
        members.sort()
    return dict(clusters), constants, unparsed


def load_formulas(path: str | Path) -> list[Row]:
    """Load formula rows from Saba's extracted_formulas.json format.

    Expects a JSON array of objects with "sheet", "cell_reference", and
    "formula" keys, and returns them as (sheet, address, content) tuples.
    A null "formula" (used by some extractors for blank cells) is treated
    as an empty string rather than the literal text "None". Raises
    TypeError if the file is not a JSON array, and ValueError, naming the bad entry's index, if an entry is missing a required field.
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
