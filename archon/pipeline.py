"""End-to-end audit pipeline: extracted workbook -> report.

Chains the existing modules in one call, no new analysis logic:
cluster (R1C1 AST hash) -> dependency graph (formula + VBA write edges) ->
override bugs (with downstream impact) -> circular references ->
plain-English explanations -> risk -> Contract F report + Contract B graph.

    result = run_extract(extract(path))           # from archon.ingest.xlsx
    result = run_audit(rows, workbook_id, vba)    # lower level

rows are (sheet, address, content) tuples: content is a formula ("=B2*C2")
or a hardcoded value as text. Blank content is ignored. vba is a list of
{"module": name, "code": source} dicts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any
from uuid import UUID

import networkx as nx

from archon.cluster.bugs import Bug, DependencyGraph, find_override_bugs
from archon.cluster.cycles import find_cycles, suggest_classification
from archon.cluster.engine import (
    ClusterKey,
    Clusters,
    Row,
    cluster_cells_ast,
    contiguous_runs,
    summarise,
)
from archon.contracts.bugs import BugLedgerEntry
from archon.contracts.explain import ExplanationRecord
from archon.contracts.extract import RawExtract
from archon.contracts.graph import Cycle, DagGraph, Edge, Node, Stats
from archon.explain.composer import compose_report
from archon.explain.formula_ast import Node as ExplainNode
from archon.explain.from_formula import explain_tree
from archon.explain.labels import Labels
from archon.explain.matcher import match_formula
from archon.explain.risk import score_record, to_contract_risk
from archon.explain.unmatched import rank_unmatched
from archon.formula.r1c1 import parse_address, to_r1c1
from archon.graph.graph_builder import add_vba_reads, build_graph
from archon.names import Table as NameTable
from archon.names import bound_whole_columns, expand_names, named_cells, reference_names
from archon.risk.scorecard import score_workbook

DOWNSTREAM_SAMPLE = 10
# What a user waiting on a big workbook sees, in order (STAGES[0] is the API reading the file).
STAGES = (
    "Reading the workbook",
    "Grouping copied formulas",
    "Building the dependency graph",
    "Finding overrides and circular references",
    "Explaining formulas",
    "Scoring risk and writing the report",
)
CellKey = tuple[str, str]  # (sheet, address); VBA nodes use ("", node id)


def _key(g: nx.DiGraph, n: str) -> CellKey:
    attrs = g.nodes[n]
    return (attrs["sheet"], attrs["cell"]) if "sheet" in attrs else ("", n)


def _label(key: CellKey) -> str:
    sheet, addr = key
    return f"{sheet}!{addr}" if sheet else addr


def _cell_graph(rows: list[Row], vba: Sequence[dict[str, str]]) -> nx.DiGraph:
    # whole-column references (C:C) become C1:C<last used row> so the graph can follow them
    last_row: dict[str, int] = defaultdict(int)
    for s, a, _c in rows:
        last_row[s] = max(last_row[s], parse_address(a)[0])
    formulas = [
        {"sheet": s, "cell": a, "formula": bound_whole_columns(c.strip(), s, last_row)}
        for s, a, c in rows
        if c.strip().startswith("=")
    ]
    g = build_graph({"formulas": formulas, "vba": list(vba)})
    for module in vba:
        add_vba_reads(g, module)
    return g


def _adjacency(g: nx.DiGraph, rows: list[Row]) -> DependencyGraph:
    """{cell: [cells that read it or are written by it]} for bugs and cycles.

    The graph builder keeps a range over 2000 cells as one node; each real
    cell inside such a range is linked to it here, so an override inside a
    big range still shows what it breaks.
    """
    adj: defaultdict[CellKey, list[CellKey]] = defaultdict(list)
    for u, v in g.edges():
        adj[_key(g, u)].append(_key(g, v))
    big = [(d["sheet"], d["cell"]) for _n, d in g.nodes(data=True) if d.get("type") == "range"]
    if big:
        cells: defaultdict[str, list[tuple[int, int, str]]] = defaultdict(list)
        for s, a, _c in rows:
            cells[s].append((*parse_address(a), a))
        for sheet, text in big:
            start, end = text.split(":")
            (r1, c1), (r2, c2) = parse_address(start), parse_address(end)
            for r, c, a in cells.get(sheet, ()):
                if r1 <= r <= r2 and c1 <= c <= c2:
                    adj[(sheet, a)].append((sheet, text))
    return dict(adj)


def _cluster_ids(clusters: Clusters) -> dict[ClusterKey, str]:
    """Readable, unique node id per cluster: Sheet!C2:C501 (hash suffix only on collision)."""
    ids: dict[ClusterKey, str] = {}
    used: set[str] = set()
    for key, members in sorted(clusters.items()):
        sheet, _col, cid = key
        first, last = members[0][1], members[-1][1]
        node_id = f"{sheet}!{first}" if first == last else f"{sheet}!{first}:{last}"
        if node_id in used:  # two clusters interleaved over the same span
            node_id = f"{node_id}#{cid[:8]}"
        used.add(node_id)
        ids[key] = node_id
    return ids


def _explain(
    clusters: Clusters,
    ids: dict[ClusterKey, str],
    formulas: dict[CellKey, str],
    labels: Labels,
) -> tuple[list[ExplanationRecord], list[tuple[str, str, ExplainNode]]]:
    """One explanation per cluster, using its first member as the representative,
    with every cell named by its business label ("Price (A2)")."""
    records: list[ExplanationRecord] = []
    parsed: list[tuple[str, str, ExplainNode]] = []
    for key, members in sorted(clusters.items()):
        sheet, _col, _cid = key
        node_id, first = ids[key], members[0][1]
        try:
            tree = explain_tree(formulas[(sheet, first)])
        except (ValueError, RecursionError):  # not representable: report unverified, never guess
            records.append(ExplanationRecord(node_id=node_id, status="unverified", confidence=0.0))
            continue
        parsed.append((node_id, first, tree))
        one_off = len(members) == 1  # one-off cells are named by their row label
        own = labels.cell(sheet, first, prefer_row=one_off)
        record = match_formula(node_id, first, tree, own)
        if record.status == "matched" and record.plain_english:
            raw = record.plain_english
            text = labels.relabel(raw, sheet, prefer_row=one_off)
            if own:
                starts_with_word = raw[:2].isalpha() and raw[1].islower()
                text = f"{own}: {text[0].lower() + text[1:] if starts_with_word else text}"
            record = record.model_copy(update={"plain_english": text, "business_concept": own})
        records.append(record)
    return records, parsed


def _severity(b: Bug, values: Mapping[CellKey, Any]) -> list[str]:
    """Aggravating factors of one override, each a plain-English reason.

    Severity is 1 + the number of reasons (max 5): it feeds other cells, it
    feeds 10+, it reaches another sheet, and the typed value is far (beyond
    0.5x-2x, or the opposite sign) from what the formula beside it produced,
    using the value Excel cached when the file was last saved.
    """
    reasons = []
    n = len(b.downstream)
    if n:
        reasons.append(f"feeds {n} other cell{'s' if n != 1 else ''}")
    if n >= 10:
        reasons.append("wide blast radius (10 or more cells)")
    other = sorted({s for s, _ in b.downstream if s and s != b.sheet})
    if other:
        reasons.append(f"reaches other sheets: {', '.join(other)}")
    expected = values.get((b.sheet, b.example_formula_cell))
    try:
        typed = float(b.hardcoded_value)
    except ValueError:
        typed = None
    if (
        isinstance(expected, int | float) and not isinstance(expected, bool)
        and expected and typed and not 0.5 <= typed / expected <= 2
    ):
        reasons.append(
            f"typed value {b.hardcoded_value} is far from the {expected:g} "
            f"the formula in {b.example_formula_cell} produced"
        )
    return reasons


def _ledger(
    bugs: list[Bug], values: Mapping[CellKey, Any]
) -> tuple[list[BugLedgerEntry], dict[str, list[str]]]:
    """Bugs -> Contract C bug ledger entries (sheet then position order), plus
    the reasons behind each entry's severity, keyed by bug id."""
    reasons: dict[str, list[str]] = {}

    def pos(b: Bug) -> tuple[str, int, int]:
        return (b.sheet, *parse_address(b.cell))

    entries = []
    for i, b in enumerate(sorted(bugs, key=pos), start=1):
        try:
            observed: float | str = float(b.hardcoded_value)
        except ValueError:
            observed = b.hardcoded_value
        n = len(b.downstream)
        bug_id = f"BUG-{i:03d}"
        reasons[bug_id] = _severity(b, values)
        entries.append(
            BugLedgerEntry(
                bug_id=bug_id,
                type="HARDCODED_OVERRIDE",
                sheet=b.sheet,
                address=b.cell,
                expected_r1c1=to_r1c1(b.example_formula, b.example_formula_cell),
                observed=observed,
                cluster_id=b.cluster_id,
                downstream_node_count=n,
                downstream_sample=[_label(k) for k in b.downstream[:DOWNSTREAM_SAMPLE]],
                severity=1 + len(reasons[bug_id]),
            )
        )
    return entries, reasons


def _dag(
    workbook_id: UUID,
    g: nx.DiGraph,
    clusters: Clusters,
    ids: dict[ClusterKey, str],
    formulas: dict[CellKey, str],
    labels: Labels,
    records: list[ExplanationRecord],
    unparsed: list[Row],
    ledger: list[BugLedgerEntry],
    cycles: list[dict[str, Any]],
    cells_in: int,
) -> tuple[DagGraph, dict[CellKey, str]]:
    """Collapse the cell graph to the Contract B map: clusters, flagged cells, input columns.

    Also returns where each graph cell landed (cell -> node id), so findings
    measured on cells can be shown exactly on the map.
    """
    risk = {r.node_id: to_contract_risk(score_record(r)) for r in records}
    nodes: dict[str, Node] = {}
    member_of: dict[CellKey, str] = {}

    for key, members in clusters.items():
        sheet, col, cid = key
        node_id, anchor = ids[key], members[0][1]
        for _row, addr in members:
            member_of[(sheet, addr)] = node_id
        try:
            r1c1 = to_r1c1(formulas[(sheet, anchor)], anchor)
        except ValueError:
            r1c1 = formulas[(sheet, anchor)]
        runs = contiguous_runs([r for r, _ in members])
        nodes[node_id] = Node(
            id=node_id, kind="cluster", sheet=sheet, r1c1=r1c1, anchor=anchor,
            member_count=len(members), ast_hash=cid,
            header=labels.cell(sheet, anchor, prefer_row=len(members) == 1),
            member_ranges=[f"{col}{a}" if a == b else f"{col}{a}:{col}{b}" for a, b in runs],
            risk=risk.get(node_id),
        )

    flagged = {(b.sheet, b.address): "" for b in ledger}
    flagged.update({(s, a): c for s, a, c in unparsed})
    for (sheet, addr), text in flagged.items():
        nodes[f"{sheet}!{addr}"] = Node(
            id=f"{sheet}!{addr}", kind="cell", sheet=sheet, r1c1=text, anchor=addr,
            header=labels.cell(sheet, addr, prefer_row=False),
        )

    def node_of(key: CellKey) -> str:
        sheet, addr = key
        if key in member_of:
            return member_of[key]
        if key in flagged:
            return f"{sheet}!{addr}"
        if not sheet:  # VBA procedure, or a dynamic write whose target is unknown
            kind = "vba_target" if addr.startswith("VBA_UNKNOWN:") else "input"
            nodes.setdefault(addr, Node(id=addr, kind=kind, sheet="VBA", r1c1="", anchor=addr))
            return addr
        if ":" in addr:  # range over 2000 cells, kept whole by the graph builder
            nodes.setdefault(f"{sheet}!{addr}", Node(id=f"{sheet}!{addr}", kind="input", sheet=sheet, r1c1="", anchor=addr))
            return f"{sheet}!{addr}"
        col = addr.rstrip("0123456789")
        node_id = f"{sheet}!{col}:{col}"
        old = nodes.get(node_id)
        nodes[node_id] = Node(
            id=node_id, kind="input", sheet=sheet, r1c1="", anchor=f"{col}:{col}",
            # the column's header, not the first cell's (that may be the header cell itself)
            header=old.header if old else labels.whole_columns(sheet, col, col),
            member_count=(old.member_count or 0) + 1 if old else 1,
        )
        return node_id

    placed: dict[CellKey, str] = {}

    def place(key: CellKey) -> str:
        # cached so each input cell is counted once in its column node
        if key not in placed:
            placed[key] = node_of(key)
        return placed[key]

    edges: dict[tuple[str, str], Edge] = {}
    for u, v, data in sorted(g.edges(data=True)):
        su, sv = place(_key(g, u)), place(_key(g, v))
        if su != sv:
            dynamic = v.startswith("VBA_UNKNOWN:")
            edges.setdefault((su, sv), Edge(
                source=su, target=sv, origin=data["label"],
                confidence="dynamic" if dynamic else "static",
            ))

    contract_cycles = [
        Cycle(
            id=f"CYC-{i:03d}",
            nodes=sorted({place(_parse_label(m)) for m in c["members"]}),
            classification="unclassified",
            evidence=f"suggested {c['suggested_classification']}: {c['reason']}",
        )
        for i, c in enumerate(cycles, start=1)
    ]
    ordered = [nodes[k] for k in sorted(nodes)]
    dag = DagGraph(
        schema_version="1.0", workbook_id=workbook_id, nodes=ordered,
        edges=[edges[k] for k in sorted(edges)], bugs=ledger, cycles=contract_cycles,
        stats=Stats(cells_in=cells_in, nodes_out=len(ordered),
                    compression_ratio=cells_in / len(ordered) if ordered else 0.0),
    )
    return dag, placed


def _parse_label(label: str) -> CellKey:
    sheet, _, addr = label.rpartition("!")
    return (sheet, addr)


def _spec(
    dag: DagGraph,
    records: list[ExplanationRecord],
    formulas: dict[CellKey, str],
) -> dict[str, Any]:
    """The specification document: per sheet, its inputs and every calculation
    in dependency order (inputs before the formulas that read them), with its
    explanation, exact formula, risk, what it depends on and what uses it.
    Built only from verified pipeline output; nothing is generated or guessed.
    """
    by_id = {n.id: n for n in dag.nodes}
    record = {r.node_id: r for r in records}
    bug_at = {f"{b.sheet}!{b.address}": b for b in dag.bugs}
    g = nx.DiGraph()
    g.add_nodes_from(by_id)
    g.add_edges_from((e.source, e.target) for e in dag.edges)
    # circular references collapse to one step, so every workbook has an order
    cond = nx.condensation(g)
    steps = nx.lexicographical_topological_sort(cond, key=lambda c: min(cond.nodes[c]["members"]))
    order = [m for c in steps for m in sorted(cond.nodes[c]["members"])]

    def name(node_id: str) -> str:
        if node_id.startswith("VBA_UNKNOWN:"):  # e.g. VBA_UNKNOWN:Module1:L6
            _, module, line = node_id.split(":")
            return f"a cell chosen at run time ({module}, line {line.removeprefix('L')})"
        node = by_id[node_id]
        return f"{node.header} ({node_id})" if node.header else node_id

    sheets: dict[str, dict[str, Any]] = {}
    macros: dict[str, tuple[list[str], list[str]]] = {}
    for node_id in order:
        node = by_id[node_id]
        if node.sheet == "VBA":
            if node.kind == "input":  # a procedure
                macros[node_id] = (
                    [name(t) for t in sorted(g.successors(node_id))],
                    [name(t) for t in sorted(g.predecessors(node_id))],
                )
            continue
        sheet = sheets.setdefault(node.sheet, {"name": node.sheet, "inputs": [], "calculations": []})
        used_by = [name(t) for t in sorted(g.successors(node_id))]
        if node.kind == "input":
            sheet["inputs"].append({"id": node_id, "label": node.header, "cells": node.member_count,
                                    "used_by": used_by})
            continue
        rec = record.get(node_id)
        risk = score_record(rec) if rec else None
        bug = bug_at.get(node_id)
        explanation = rec.plain_english if rec else None
        if bug:
            explanation = (
                f"{bug.bug_id}: the value {_value_text(bug.observed)} is typed in where the rest of "
                f"this column uses the formula {bug.expected_r1c1} (R1C1)."
            )
        sheet["calculations"].append({
            "id": node_id,
            "label": node.header,
            "cells": node.member_ranges or [node.anchor],
            "count": node.member_count or 1,
            "formula": formulas.get((node.sheet, node.anchor), node.r1c1),
            "explanation": explanation,
            "risk_score": risk.score if risk else 0,
            "risk_flags": list(risk.flags) if risk else [],
            "depends_on": [name(p) for p in sorted(g.predecessors(node_id))],
            "used_by": used_by,
            "is_output": not used_by,
            # flagged cells: a typed-over value (no formula) or a formula we couldn't parse
            "kind": ("override" if not node.r1c1 else "unparsed") if node.kind == "cell" else node.kind,
        })
    return {
        "sheets": [sheets[k] for k in sorted(sheets)],
        "macros": [
            {"procedure": p, "writes_to": w, "reads_from": r} for p, (w, r) in sorted(macros.items())
        ],
    }


_ON_ERROR_RESUME = re.compile(r"^\s*On\s+Error\s+Resume\s+Next\b", re.IGNORECASE | re.MULTILINE)


def _vba_findings(
    vba: Sequence[dict[str, str]], g: nx.DiGraph, unknown_writes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Macro behaviour an auditor must see, each with where it happens.

    - error_suppression: 'On Error Resume Next' hides every failure after it
    - overwrites_formula: a macro writes a value into a cell that holds a formula
    - dynamic_write: a macro writes to a cell decided at run time (untraceable)
    """
    found: list[dict[str, Any]] = []
    for module in vba:
        proc = "(module)"
        for number, raw in enumerate(module["code"].splitlines(), start=1):
            head = _PROC.match(raw)
            if head:
                proc = head[1]
            if _ON_ERROR_RESUME.match(raw):
                found.append({"kind": "error_suppression", "module": module["module"],
                              "procedure": proc, "line": number, "text": raw.strip()})
    for u, v, d in g.edges(data=True):
        if d["label"] == "vba_write" and g.nodes[v].get("type") == "formula":
            p = g.nodes[u]
            found.append({"kind": "overwrites_formula", "module": p["module"],
                          "procedure": p["procedure"], "cell": v,
                          "text": f"writes a value into {v}, which holds the formula {g.nodes[v]['formula']}"})
    found += [{"kind": "dynamic_write", **w} for w in unknown_writes]
    rank = {"overwrites_formula": 0, "error_suppression": 1, "dynamic_write": 2}  # most damaging first
    return sorted(found, key=lambda f: (rank[f["kind"]], f["module"], f["procedure"],
                                        str(f.get("line", f.get("cell")))))


_PROC = re.compile(r"^\s*(?:(?:Public|Private|Friend)\s+)?(?:Static\s+)?(?:Sub|Function)\s+(\w+)", re.IGNORECASE)


def _scorecard_counts(
    bugs: list[BugLedgerEntry],
    cycles: list[dict[str, Any]],
    records: list[ExplanationRecord],
    unparsed: list[Row],
    vba: Sequence[dict[str, str]],
    g: nx.DiGraph,
    dag: DagGraph,
    context: dict[str, int],
) -> dict[str, int]:
    """Signal counts for the workbook scorecard (archon/risk/scorecard.yaml)."""
    sheet_of = {n.id: n.sheet for n in dag.nodes}
    blocks = len(records) + len(unparsed)
    unexplained = sum(r.status == "unverified" for r in records) + len(unparsed)
    vba_edges = [v for _u, v, d in g.edges(data=True) if d["label"] == "vba_write"]
    return {
        "override_bug": len(bugs),
        "cycle": len(cycles),
        "flagged_block_score": sum(score_record(r).score for r in records if r.status == "matched"),
        "vba_module": len(vba),
        "vba_100_lines": sum(len(m["code"].splitlines()) for m in vba) // 100,
        "vba_write": sum(not v.startswith("VBA_UNKNOWN:") for v in vba_edges),
        "vba_dynamic_write": sum(v.startswith("VBA_UNKNOWN:") for v in vba_edges),
        "vba_error_suppression": sum(len(_ON_ERROR_RESUME.findall(m["code"])) for m in vba),
        "external_link": context.get("external_links", 0),
        "cross_sheet_link": sum(
            e.origin == "formula" and sheet_of[e.source] != sheet_of[e.target] for e in dag.edges
        ),
        "hidden_sheet": context.get("hidden_sheets", 0),
        "very_hidden_sheet": context.get("very_hidden_sheets", 0),
        "unexplained_pct": round(100 * unexplained / blocks) if blocks else 0,
    }


def run_audit(
    rows: Iterable[Row],
    workbook_id: UUID,
    vba: Sequence[dict[str, str]] = (),
    context: dict[str, int] | None = None,
    values: Mapping[CellKey, Any] | None = None,
    names: NameTable | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run every analysis stage and return one JSON-ready result.

    progress, if given, is called with a short stage name as each stage starts.

    context carries workbook facts the cells don't show: counts of
    hidden_sheets, very_hidden_sheets and external_links (see run_extract).
    values maps formula cells to the result Excel cached for them, used to
    judge how far an override is from what its formula would give.
    names (archon.names.reference_names) expands named ranges such as
    TaxRate into the cells they stand for; the formulas shown keep the names.
    """
    rows = [(s, a, str(c)) for s, a, c in rows if str(c).strip()]
    as_written = {(s, a): c.strip() for s, a, c in rows if c.strip().startswith("=")}
    rows = [(s, a, expand_names(c.strip(), s, names or {})) for s, a, c in rows]
    step = progress or (lambda _stage: None)
    step(STAGES[1])
    clusters, constants, unparsed = cluster_cells_ast(rows)
    step(STAGES[2])
    g = _cell_graph(rows, vba)
    graph = _adjacency(g, rows)
    formulas = {(s, a): c.strip() for s, a, c in rows if c.strip().startswith("=")}
    labels = Labels(rows, named_cells(names or {}))

    step(STAGES[3])
    found_bugs = find_override_bugs(rows, clusters, constants, graph=graph)
    bugs, severity_reasons = _ledger(found_bugs, values or {})

    cycles = []
    # Circular references are about formulas: a macro that reads and rewrites a
    # cell (Range("A1") = Range("A1") + 1) is a stateful update, not a cycle.
    formula_graph = {
        k: [v for v in vs if v[0]] for k, vs in graph.items() if k[0]
    }
    for cycle in find_cycles(formula_graph):
        label, reason = suggest_classification(cycle, formulas)
        cycles.append({
            "members": sorted(_label(k) for k in cycle.members),
            "suggested_classification": label,
            "reason": reason,
            "classification": None,  # set only by a human reviewer (see cycles.classify_cycle)
        })
    cycles.sort(key=lambda c: c["members"])

    step(STAGES[4])
    ids = _cluster_ids(clusters)
    records, parsed = _explain(clusters, ids, formulas, labels)
    report = compose_report(workbook_id, records, unmatched_shapes=rank_unmatched(parsed))
    step(STAGES[5])
    dag, placed = _dag(workbook_id, g, clusters, ids, formulas, labels, records, unparsed, bugs, cycles, len(rows))
    # Blocks a bug really affects: its downstream cells mapped to their blocks.
    # (Following block-to-block links instead would overstate the impact, since a
    # block reached through one cell has successors through all of its cells.)
    bug_id_at = {(b.sheet, b.address): b.bug_id for b in bugs}
    affected = {
        bug_id_at[(b.sheet, b.cell)]: sorted({placed[k] for k in b.downstream if k in placed})
        for b in found_bugs
    }

    unknown_writes = [
        {k: d[k] for k in ("module", "procedure", "line", "text", "reason")}
        for _n, d in sorted(g.nodes(data=True))
        if d.get("type") == "vba_write_range_unknown"
    ]
    vba_findings = _vba_findings(vba, g, unknown_writes)
    stats = summarise(clusters, constants)
    total_formulas = stats["formula_cells"] + len(unparsed)
    scorecard = score_workbook(
        _scorecard_counts(bugs, cycles, records, unparsed, vba, g, dag, context or {})
    )
    return {
        "scorecard": scorecard,
        "summary": {
            **stats,
            "unparsed_formulas": len(unparsed),
            "parse_failure_rate": len(unparsed) / total_formulas if total_formulas else 0.0,
            "override_bugs": len(bugs),
            "cycles": len(cycles),
            "vba_dynamic_writes": len(unknown_writes),
            "explained_clusters": sum(r.status == "matched" for r in records),
            "unverified_clusters": sum(r.status == "unverified" for r in records),
        },
        "bugs": [
            {**b.model_dump(mode="json"), "severity_reasons": severity_reasons[b.bug_id],
             "affected_nodes": affected[b.bug_id]}
            for b in bugs
        ],
        "cycles": cycles,
        "vba_unknown_writes": unknown_writes,
        "vba_findings": vba_findings,
        "unparsed": [{"sheet": s, "cell": a, "formula": c} for s, a, c in unparsed],
        "graph": dag.model_dump(mode="json"),
        "spec": _spec(dag, records, as_written),
        "report": report.model_dump(mode="json"),
    }


def _value_text(value: float | str | bool) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value)
    # a text value that merely looks like a formula must not be analysed as one
    return "'" + text if text.startswith("=") else text


def _vba_inputs(raw: RawExtract) -> list[dict[str, str]]:
    """VBA modules for the graph. In a sheet's own module an unqualified
    Range("A1") (or Me.Range) means that sheet, so it becomes the default."""
    sheet_of = {s.code_name: s.name for s in raw.sheets if s.code_name}
    out = []
    for m in raw.vba_modules:
        module = {"module": m.name, "code": m.source}
        own = sheet_of.get(m.name.rsplit(".", 1)[0]) if m.type == "sheet" else None
        if own:
            module["default_sheet"] = own
        out.append(module)
    return out


def run_extract(raw: RawExtract, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Audit a Contract A extract (archon.ingest.xlsx.extract) end to end."""
    rows: list[Row] = [
        (c.sheet, c.address, c.formula if c.formula else _value_text(c.cached_value))
        for c in raw.cells
        if c.formula or c.cached_value is not None
    ]
    vba = _vba_inputs(raw)
    context = {
        "hidden_sheets": sum(s.visibility == "hidden" for s in raw.sheets),
        "very_hidden_sheets": sum(s.visibility == "veryHidden" for s in raw.sheets),
        "external_links": len(raw.external_links),
    }
    values = {(c.sheet, c.address): c.cached_value for c in raw.cells if c.formula}
    names = reference_names(raw.defined_names, [s.name for s in sorted(raw.sheets, key=lambda s: s.index)])
    result = run_audit(rows, raw.workbook_id, vba, context, values, names, progress)
    # present the specification in the workbook's own sheet order
    order = {s.name: s.index for s in raw.sheets}
    result["spec"]["sheets"].sort(key=lambda x: (order.get(x["name"], len(order)), x["name"]))
    result["extract"] = {
        "source": raw.source.model_dump(mode="json"),
        "sheets": [
            {"name": s.name, "visibility": s.visibility, "dimensions": s.dimensions}
            for s in raw.sheets
        ],
        "cell_count": len(raw.cells),
        "formula_count": sum(c.formula is not None for c in raw.cells),
        "vba_modules": [
            {"name": m.name, "type": m.type, "line_count": m.line_count} for m in raw.vba_modules
        ],
        "exceptions": [e.model_dump(mode="json") for e in raw.exceptions],
    }
    return result
