"""Deterministic structural matcher: formula AST -> ExplanationRecord.

Idioms live in patterns/*.yaml. Each pattern names a structural `shape`;
shapes are the only code. A new idiom of an existing shape is a data change.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from archon.contracts.explain import Evidence, ExplanationRecord
from archon.explain.formula_ast import BinOp, Call, Node, Num, Ref, prior_row_address

PATTERN_DIR = Path(__file__).parent / "patterns"
COMPARE_OPS = ("<", "<=", ">", ">=", "=", "<>")
Spec = dict[str, Any]
Captured = dict[str, str]


@lru_cache(maxsize=1)
def load_patterns() -> tuple[Spec, ...]:
    """Load every pattern file, sorted by file name then by pattern id."""
    specs: list[Spec] = []
    for path in sorted(PATTERN_DIR.glob("*.yaml")):
        specs.extend(yaml.safe_load(path.read_text(encoding="utf-8"))["patterns"])
    return tuple(sorted(specs, key=lambda spec: spec["id"]))


def _leaf_text(node: Node) -> str | None:
    """Text of a number or cell reference; None for anything else."""
    if isinstance(node, Num):
        return node.text
    if isinstance(node, Ref):
        return node.address
    return None


def _ladder_step(node: Call) -> tuple[str, str, str, str, Node] | None:
    """Read one IF(pivot <op> threshold, rate, rest) level."""
    if len(node.args) != 3:
        return None
    cond, then, rest = node.args
    if not (
        isinstance(cond, BinOp)
        and cond.op in COMPARE_OPS
        and isinstance(cond.left, Ref)
    ):
        return None
    threshold, rate = _leaf_text(cond.right), _leaf_text(then)
    if threshold is None or rate is None:
        return None
    return cond.left.address, cond.op, threshold, rate, rest


def _match_ladder(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """Nested IF ladder, min_depth levels, one pivot, one comparison operator."""
    brackets: list[str] = []
    key: tuple[str, str] | None = None
    node = tree
    while isinstance(node, Call) and node.name == spec["function"]:
        step = _ladder_step(node)
        if step is None:
            return None
        pivot, op, threshold, rate, node = step
        if key is not None and key != (pivot, op):
            return None
        key = (pivot, op)
        brackets.append(f"{threshold}:{rate}")
    default = _leaf_text(node)
    if key is None or default is None or len(brackets) < spec["min_depth"]:
        return None
    return {
        "pivot": key[0],
        "brackets": "|".join([*brackets, f"default:{default}"]),
        "bracket_count": str(len(brackets) + 1),
    }


def _flatten(node: Node, sign: int = 1) -> Iterator[tuple[int, Node]]:
    """Yield (sign, term) for a tree of + and - operations, left to right."""
    if isinstance(node, BinOp) and node.op in ("+", "-"):
        yield from _flatten(node.left, sign)
        yield from _flatten(node.right, sign if node.op == "+" else -sign)
    else:
        yield sign, node


def _match_chain(tree: Node, cell_address: str, spec: Spec) -> Captured | None:
    """Sum of cell refs where the cell one row above, same column, is added once."""
    cell = cell_address.upper()
    prior = prior_row_address(cell)
    terms = list(_flatten(tree))
    refs = [(sign, term.address) for sign, term in terms if isinstance(term, Ref)]
    if prior is None or len(terms) < 2 or len(refs) != len(terms):
        return None
    addresses = [address for _, address in refs]
    if addresses.count(prior) != 1 or (1, prior) not in refs or cell in addresses:
        return None
    return {
        "prior_row": prior,
        "added": ", ".join(a for s, a in refs if s == 1 and a != prior),
        "subtracted": ", ".join(a for s, a in refs if s == -1),
    }


SHAPES: dict[str, Callable[[Node, str, Spec], Captured | None]] = {
    "if_ladder": _match_ladder,
    "additive_chain": _match_chain,
}


def _render(spec: Spec, captured: Captured) -> str:
    """Fill the pattern's sentence template; empty optional clauses vanish."""
    context: dict[str, str] = dict(captured)
    for key, clause in sorted(spec.get("clauses", {}).items()):
        context[f"{key}_clause"] = clause.format(**captured) if captured[key] else ""
    return spec["template"].format(**context)


def match_formula(node_id: str, cell_address: str, tree: Node) -> ExplanationRecord:
    """Explain a formula, or return an unverified record. Never guesses."""
    for spec in load_patterns():
        captured = SHAPES[spec["shape"]](tree, cell_address, spec)
        if captured is not None:
            return ExplanationRecord(
                node_id=node_id,
                status="matched",
                idiom=spec["idiom"],
                plain_english=_render(spec, captured),
                evidence=Evidence(
                    pattern_id=spec["id"],
                    captured_vars=captured,
                    header_resolved=False,
                ),
                confidence=1.0,
            )
    return ExplanationRecord(node_id=node_id, status="unverified", confidence=0.0)
