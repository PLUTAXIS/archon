"""AST node types for parsed Excel formulas.

These are the building blocks the parser (archon/formula/parser.py) produces
and everything downstream (R1C1 translation, clustering, codegen) consumes.

frozen=True + slots=True matters at scale: immutable nodes are safe to share
and hash, and slots keep memory down across hundreds of thousands of cells.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Lit:
    """A literal constant: a number, string, or boolean written directly in the formula."""

    value: float | str | bool


@dataclass(frozen=True, slots=True)
class Ref:
    """A cell or range reference.

    sheet: the sheet name, or None if the reference has no explicit sheet
        (it belongs to whatever sheet the formula itself is on).
    r1c1: the reference in R1C1 text form, e.g. "RC[-2]" or "R2C2:RC[-1]".
    absolute: (row_absolute, col_absolute) — whether each axis is a fixed
        reference ($A$1-style) rather than relative to the formula's cell.
    """

    sheet: str | None
    r1c1: str
    absolute: tuple[bool, bool]


@dataclass(frozen=True, slots=True)
class UnaryOp:
    """A prefix or postfix unary operation: unary minus (-A1) or percent (50%)."""

    op: str
    operand: Node
    postfix: bool = False


@dataclass(frozen=True, slots=True)
class BinOp:
    """A binary operation: arithmetic (+ - * / ^), comparison, concatenation (&),
    or a reference operator (: range, (space) intersection, , union).
    """

    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Func:
    """A function call, e.g. SUM(A1:A10) or IF(A1>0, B1, 0)."""

    name: str
    args: tuple[Node, ...]


Node = BinOp | UnaryOp | Func | Ref | Lit
