"""Override-bug detection: find cells where a dragged formula was replaced
by a hardcoded value, and trace every downstream cell that depends on it.

Per the brief (section B): clustering *is* the detector. If 9,999 rows in a
column share a cluster and row 4,312 is a constant sandwiched inside that
cluster's row range, that row is an override bug. The brief also asks for,
per bug, the downstream nodes that depend on it -- "Row 4,312 is hardcoded,
and every total downstream of it has been wrong since it was entered" is
what sells the finding, not just "row 4,312 is hardcoded".

Downstream tracing needs a cell dependency graph, which is Mainak's domain
(dag_graph.json / NetworkX -- the graph's exact format is still "to confirm
with Senpai" per PROGRESS.md as of this module). To stay decoupled from
that still-unconfirmed format, this module takes a plain adjacency mapping
instead of Mainak's graph object directly: pass whatever mapping he settles
on, converted to
    {(sheet, address): [(sheet, address), ...]}
meaning "cell -> cells that directly depend on it" (an edge A -> B means
B's formula reads cell A). Downstream tracing is optional -- call without a
graph to get bugs with no downstream info, flagged as such.

    clusters, constants, _ = cluster_cells_ast(rows)
    bugs = find_override_bugs(rows, clusters, constants, graph=dep_graph)
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from archon.cluster.engine import ClusterKey, Clusters, Constant, Row
from archon.formula.r1c1 import num_to_col, parse_address

CellId = tuple[str, str]
DependencyGraph = Mapping[CellId, Sequence[CellId]]


@dataclass(frozen=True, slots=True)
class Bug:
    """One override: a hardcoded value sitting inside a dragged cluster.

    example_formula/example_formula_cell are the nearest cluster member's
    own formula and address -- a concrete instance of "the formula that
    should be there", shown as that neighbor actually wrote it (its own
    A1 text), not re-anchored to this bug's own cell. Re-anchoring would
    need the old text-based to_a1() round-trip; left as a documented,
    deliberate simplification rather than built now (out of this module's
    scope -- see r1c1.py for the anchor-aware primitives it would use).
    downstream is every cell transitively dependent on this one, in BFS
    order, deduplicated -- empty if no dependency graph was supplied, in
    which case downstream_traced is False so callers can tell "verified
    no downstream impact" apart from "impact not checked".
    """

    sheet: str
    cell: str
    cluster_id: str
    example_formula: str
    example_formula_cell: str
    hardcoded_value: str
    downstream: tuple[CellId, ...]
    downstream_traced: bool


def _trace_downstream(graph: DependencyGraph, start: CellId) -> tuple[CellId, ...]:
    """BFS every cell transitively dependent on start, start excluded.

    Cycle-safe: a cell already seen is never re-queued, so a circular
    formula reference in the graph can't loop forever.
    """
    seen = {start}
    order: list[CellId] = []
    queue: deque[CellId] = deque()
    for nxt in graph.get(start, ()):
        if nxt not in seen:
            seen.add(nxt)
            queue.append(nxt)
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in graph.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return tuple(order)


def find_override_bugs(
    rows: Iterable[Row],
    clusters: Clusters,
    constants: list[Constant],
    graph: DependencyGraph | None = None,
) -> list[Bug]:
    """Find constants that are override bugs, and trace their downstream impact.

    A constant is an override bug only if it sits in the same (sheet,
    column) as an existing cluster AND its row falls within that cluster's
    row span -- i.e. it's sandwiched inside a dragged range, not just some
    unrelated input cell that happens to hold a number. A constant in the
    same column but above/below every cluster member (e.g. a header or a
    totals row) is not flagged. If a constant's row falls within more than
    one cluster's span in the same column (rare -- e.g. two different
    dragged formulas interleaved), the cluster with the most members is
    used, since it's the more confident "this is the pattern" call.
    """
    formula_lookup: dict[CellId, str] = {}
    for sheet, addr, content in rows:
        text = str(content).strip()
        if text.startswith("="):
            formula_lookup[(sheet, addr)] = text

    by_col: defaultdict[tuple[str, str], list[tuple[ClusterKey, list[tuple[int, str]], int, int]]] = (
        defaultdict(list)
    )
    for key, members in clusters.items():
        sheet, col, _cid = key
        rows_only = [r for r, _ in members]
        by_col[(sheet, col)].append((key, members, min(rows_only), max(rows_only)))

    bugs: list[Bug] = []
    for sheet, addr, value in constants:
        try:
            row, col_num = parse_address(addr)
        except ValueError:
            continue
        col = num_to_col(col_num)
        candidates = [c for c in by_col.get((sheet, col), ()) if c[2] <= row <= c[3]]
        if not candidates:
            continue
        key, members, _lo, _hi = max(candidates, key=lambda c: len(c[1]))
        nearest_row, nearest_addr = min(members, key=lambda m: abs(m[0] - row))
        example_formula = formula_lookup.get((sheet, nearest_addr), "")

        if graph is not None:
            downstream = _trace_downstream(graph, (sheet, addr))
            traced = True
        else:
            downstream = ()
            traced = False

        bugs.append(
            Bug(
                sheet=sheet,
                cell=addr,
                cluster_id=key[2],
                example_formula=example_formula,
                example_formula_cell=nearest_addr,
                hardcoded_value=value,
                downstream=downstream,
                downstream_traced=traced,
            )
        )
    return bugs
