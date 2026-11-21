"""End-to-end audit pipeline: extracted cells -> report.

Chains the existing modules in one call, no new analysis logic:
cluster (R1C1 AST hash) -> dependency graph -> override bugs (with downstream
impact) -> circular references -> plain-English explanations -> risk ->
Contract F report.

    result = run_audit(rows, workbook_id)

rows are (sheet, address, content) tuples: content is a formula ("=B2*C2")
or a hardcoded value as text. Blank content is ignored.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from archon.cluster.bugs import Bug, DependencyGraph, find_override_bugs
from archon.cluster.cycles import find_cycles, suggest_classification
from archon.cluster.engine import Clusters, Row, cluster_cells_ast, summarise
from archon.contracts.bugs import BugLedgerEntry
from archon.contracts.explain import ExplanationRecord
from archon.explain.composer import compose_report
from archon.explain.formula_ast import Node, parse_mock_formula
from archon.explain.matcher import match_formula
from archon.explain.unmatched import rank_unmatched
from archon.formula.r1c1 import parse_address, to_r1c1
from archon.graph.graph_builder import build_graph

DOWNSTREAM_SAMPLE = 10


def _dependency_graph(rows: list[Row]) -> DependencyGraph:
    """Adjacency {cell: [cells that read it]} from the graph builder's DiGraph."""
    formulas = [
        {"sheet": s, "cell": a, "formula": c.strip()}
        for s, a, c in rows
        if c.strip().startswith("=")
    ]
    g = build_graph({"formulas": formulas, "vba": []})
    adj: defaultdict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for u, v in g.edges():
        nu, nv = g.nodes[u], g.nodes[v]
        adj[(nu["sheet"], nu["cell"])].append((nv["sheet"], nv["cell"]))
    # shortcut: a constant inside a range over 2000 cells (collapsed to one node) shows no downstream; trace range membership if that hides real impact.
    return dict(adj)


def _headers(rows: list[Row]) -> dict[tuple[str, str], str]:
    """Row-1 text labels per (sheet, column letters), used as business headers."""
    out: dict[tuple[str, str], str] = {}
    for sheet, addr, content in rows:
        text = content.strip()
        row, _ = parse_address(addr)
        if row == 1 and text and not text.startswith("=") and not _is_number(text):
            out[(sheet, addr.rstrip("0123456789").replace("$", "").upper())] = text
    return out


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _explain(
    clusters: Clusters, formulas: dict[tuple[str, str], str], headers: dict[tuple[str, str], str]
) -> tuple[list[ExplanationRecord], list[tuple[str, str, Node]]]:
    """One explanation per cluster, using its first member as the representative."""
    records: list[ExplanationRecord] = []
    parsed: list[tuple[str, str, Node]] = []
    used: set[str] = set()
    for (sheet, col, cid), members in sorted(clusters.items()):
        first, last = members[0][1], members[-1][1]
        node_id = f"{sheet}!{first}" if first == last else f"{sheet}!{first}:{last}"
        if node_id in used:  # two clusters interleaved over the same span
            node_id = f"{node_id}#{cid[:8]}"
        used.add(node_id)
        try:
            tree = parse_mock_formula(formulas[(sheet, first)])
        except ValueError:  # matcher's parser can't read it: report as unverified, never guess
            records.append(ExplanationRecord(node_id=node_id, status="unverified", confidence=0.0))
            continue
        parsed.append((node_id, first, tree))
        records.append(match_formula(node_id, first, tree, headers.get((sheet, col))))
    return records, parsed


def _ledger(bugs: list[Bug]) -> list[BugLedgerEntry]:
    """Bugs -> Contract bug ledger entries, ordered by sheet then position."""
    def pos(b: Bug) -> tuple[str, int, int]:
        return (b.sheet, *parse_address(b.cell))

    entries = []
    for i, b in enumerate(sorted(bugs, key=pos), start=1):
        try:
            observed: float | str = float(b.hardcoded_value)
        except ValueError:
            observed = b.hardcoded_value
        n = len(b.downstream)
        entries.append(
            BugLedgerEntry(
                bug_id=f"BUG-{i:03d}",
                type="HARDCODED_OVERRIDE",
                sheet=b.sheet,
                address=b.cell,
                expected_r1c1=to_r1c1(b.example_formula, b.example_formula_cell),
                observed=observed,
                cluster_id=b.cluster_id,
                downstream_node_count=n,
                downstream_sample=[f"{s}!{a}" for s, a in b.downstream[:DOWNSTREAM_SAMPLE]],
                # shortcut: severity is a placeholder (5 = wide blast radius, 4 = some, 3 = none); replace with Sneha's risk weights when agreed.
                severity=5 if n >= 10 else 4 if n else 3,
            )
        )
    return entries


def run_audit(rows: Iterable[Row], workbook_id: UUID) -> dict[str, Any]:
    """Run every analysis stage and return one JSON-ready result."""
    rows = [(s, a, str(c)) for s, a, c in rows if str(c).strip()]
    clusters, constants, unparsed = cluster_cells_ast(rows)
    graph = _dependency_graph(rows)
    formulas = {(s, a): c.strip() for s, a, c in rows if c.strip().startswith("=")}

    bugs = _ledger(find_override_bugs(rows, clusters, constants, graph=graph))

    cycles = []
    for cycle in find_cycles(graph):
        label, reason = suggest_classification(cycle, formulas)
        cycles.append({
            "members": sorted(f"{s}!{a}" for s, a in cycle.members),
            "suggested_classification": label,
            "reason": reason,
            "classification": None,  # set only by a human reviewer (see cycles.classify_cycle)
        })
    cycles.sort(key=lambda c: c["members"])

    records, parsed = _explain(clusters, formulas, _headers(rows))
    report = compose_report(workbook_id, records, unmatched_shapes=rank_unmatched(parsed))

    stats = summarise(clusters, constants)
    total_formulas = stats["formula_cells"] + len(unparsed)
    return {
        "summary": {
            **stats,
            "unparsed_formulas": len(unparsed),
            "parse_failure_rate": len(unparsed) / total_formulas if total_formulas else 0.0,
            "override_bugs": len(bugs),
            "cycles": len(cycles),
            "explained_clusters": sum(r.status == "matched" for r in records),
            "unverified_clusters": sum(r.status == "unverified" for r in records),
        },
        "bugs": [b.model_dump(mode="json") for b in bugs],
        "cycles": cycles,
        "unparsed": [{"sheet": s, "cell": a, "formula": c} for s, a, c in unparsed],
        "report": report.model_dump(mode="json"),
    }
