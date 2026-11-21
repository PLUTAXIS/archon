"""Unmatched-shapes report: which formula shapes the engine could not explain."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from archon.explain.formula_ast import BinOp, Node, Num, Range, Ref, Str
from archon.explain.matcher import match_formula


@dataclass(frozen=True)
class ShapeCount:
    """One unmatched shape and how many formulas share it."""

    shape: str
    count: int


def shape_key(node: Node) -> str:
    """Canonical structure of a formula, ignoring which cells it references."""
    if isinstance(node, Num):
        return "<num>"
    if isinstance(node, Ref):
        return "<ref>"
    if isinstance(node, Range):
        return "<range>"
    if isinstance(node, Str):
        return "<str>"
    if isinstance(node, BinOp):
        return f"({shape_key(node.left)}{node.op}{shape_key(node.right)})"
    return f"{node.name}({','.join(shape_key(a) for a in node.args)})"


def rank_unmatched(
    items: Iterable[tuple[str, str, Node]],
) -> tuple[ShapeCount, ...]:
    """Count unmatched shapes, most frequent first, ties broken alphabetically.

    Each item is (node_id, cell_address, formula tree). Matched formulas are
    excluded. The result does not depend on input order.
    """
    counts: Counter[str] = Counter()
    for node_id, cell, tree in items:
        if match_formula(node_id, cell, tree).status == "unverified":
            counts[shape_key(tree)] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(ShapeCount(shape, count) for shape, count in ranked)
