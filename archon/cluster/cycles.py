"""Circular formula loop detection (Tarjan's SCC algorithm) and labeling.

Per the brief (section C): run Tarjan's strongly-connected-components
algorithm over the dependency graph to find circular formula references,
then make the judgment call the algorithm cannot -- is this intentional
model logic (a deliberate iterative calculation, common in financial
models for interest, depreciation, circular tax calcs) or a user error?
Every cycle must be labeled one or the other before it ships; an
unclassified cycle is explicitly called out as worse than no finding at
all (see the brief's own warning about looking like we don't understand
finance).

This module gives you two separate things, deliberately not one:

1. find_cycles(graph) -- objective, algorithmic: the actual strongly
   connected components of size > 1, plus true self-loops, found by
   Tarjan's algorithm. This part the algorithm CAN do reliably.

2. suggest_classification(cycle, formulas) -- a heuristic SUGGESTION only,
   never authoritative, never silently trusted. It looks for function
   names commonly associated with deliberate iterative calculation (IRR,
   XIRR, RATE, NPER, PMT) inside the cycle's own formulas and suggests
   "logic" if found, "error" otherwise -- with a reason string explaining
   why, so a human can agree or override it. This is the part the brief
   says the algorithm cannot really do; this function is named
   "suggest_", not "classify_", on purpose, so nothing downstream can
   mistake a guess for a verified label.

classify_cycle(cycle, label, note) is the actual labeling step: it's how
a human's judgment call gets recorded, turning a cycle's classification
from None into "logic" or "error" for good. Nothing should treat a cycle
as resolved while its classification is still None.

Tarjan's algorithm is implemented iteratively here, not with the textbook
recursive formulation, since a 500,000-cell file (see the brief's own
scale) could nest far deeper than Python's default recursion limit, the
same RecursionError risk already documented and guarded against in
archon.formula.parser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

CellId = tuple[str, str]
DependencyGraph = Mapping[CellId, Sequence[CellId]]

Classification = Literal["logic", "error"]

_ITERATIVE_FUNCS = frozenset({"IRR", "XIRR", "RATE", "NPER", "PMT"})
_ITERATIVE_RE = re.compile(
    r"(?<![A-Z0-9_.])(" + "|".join(sorted(_ITERATIVE_FUNCS)) + r")\("
)


@dataclass(frozen=True, slots=True)
class Cycle:
    """One circular formula loop: a set of cells that depend on each other.

    members has no defined order (it's the strongly connected component
    as a frozenset) -- a true cycle always has at least one cell, and more
    than one unless it's a direct self-reference (a cell whose formula
    reads its own address). classification is None until a human (or
    classify_cycle) sets it; nothing in this module ever sets it to a real
    value on its own, since that call is explicitly not the algorithm's to
    make.
    """

    members: frozenset[CellId]
    classification: Classification | None = None
    note: str = ""


def find_cycles(graph: DependencyGraph) -> list[Cycle]:
    """Find every circular formula reference in a dependency graph.

    graph is the same adjacency shape used by archon.cluster.bugs:
    {(sheet, address): [(sheet, address), ...]}, an edge A -> B meaning
    B's formula reads cell A (B depends on A). Returns one Cycle per
    strongly connected component of size > 1, plus any single-cell
    component that has a direct self-edge (a formula that reads its own
    cell, e.g. "=A1+1" written in A1) -- both are real circular
    references; a single-cell component with no self-edge is just an
    ordinary non-circular cell and is not returned.

    Implemented iteratively (an explicit stack, not Python call recursion)
    so a very large or very deep dependency graph can't raise
    RecursionError -- see the module docstring.
    """
    index_counter = [0]
    index: dict[CellId, int] = {}
    lowlink: dict[CellId, int] = {}
    on_stack: dict[CellId, bool] = {}
    stack: list[CellId] = []
    sccs: list[frozenset[CellId]] = []

    all_nodes: list[CellId] = []
    seen_nodes: set[CellId] = set()
    for node in graph.keys():
        if node not in seen_nodes:
            seen_nodes.add(node)
            all_nodes.append(node)
    for dependents in graph.values():
        for dep in dependents:
            if dep not in seen_nodes:
                seen_nodes.add(dep)
                all_nodes.append(dep)

    for start in all_nodes:
        if start in index:
            continue

        # Each work-stack frame is (node, iterator-position-over-neighbors).
        work: list[tuple[CellId, int]] = [(start, 0)]
        index[start] = index_counter[0]
        lowlink[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack[start] = True

        while work:
            node, i = work[-1]
            neighbors = graph.get(node, ())
            if i < len(neighbors):
                work[-1] = (node, i + 1)
                nxt = neighbors[i]
                if nxt not in index:
                    index[nxt] = index_counter[0]
                    lowlink[nxt] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(nxt)
                    on_stack[nxt] = True
                    work.append((nxt, 0))
                elif on_stack.get(nxt, False):
                    lowlink[node] = min(lowlink[node], index[nxt])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == index[node]:
                    component: list[CellId] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        component.append(w)
                        if w == node:
                            break
                    sccs.append(frozenset(component))

    cycles: list[Cycle] = []
    for component in sccs:
        if len(component) > 1:
            cycles.append(Cycle(members=component))
        else:
            (only,) = component
            if only in graph.get(only, ()):
                cycles.append(Cycle(members=component))
    return cycles


def suggest_classification(
    cycle: Cycle, formulas: Mapping[CellId, str]
) -> tuple[Classification, str]:
    """Suggest, but do not decide, whether a cycle is intentional or a bug.

    This is a heuristic ONLY -- see the module docstring. formulas maps
    each cell to its formula text (e.g. from load_formulas()). Looks for
    any of IRR/XIRR/RATE/NPER/PMT in the cycle members' own formula text,
    which commonly indicates a deliberate iterative financial calculation.
    Found -> suggests "logic". Not found -> suggests "error", since most
    accidental circular references have no such function and are typos
    or copy-paste mistakes, but this is the weaker, default guess and
    should get the most scrutiny, not the least.
    """
    found: set[str] = set()
    for cell in cycle.members:
        text = formulas.get(cell, "").upper()
        found.update(_ITERATIVE_RE.findall(text))
    if found:
        names = ", ".join(sorted(found))
        return "logic", f"Found iterative-calculation function(s) {names} in cycle"
    return "error", "No iterative-calculation function names found in cycle; verify manually"


def classify_cycle(cycle: Cycle, classification: Classification, note: str = "") -> Cycle:
    """Record a human's classification decision for one cycle.

    This is the only place a Cycle's classification should actually be
    set to a real value -- find_cycles() never sets it, and
    suggest_classification() only proposes one. Returns a new Cycle (Cycle
    is frozen); the input is not mutated.
    """
    return replace(cycle, classification=classification, note=note)
