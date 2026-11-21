"""Adapter: Senpai's full parser (archon.formula) -> the explain AST.

The explain layer's own parser (formula_ast.parse_mock_formula) reads only a
small grammar. This lets the matcher see formulas it rejects, such as
sheet-qualified refs (Inputs!B2), unary minus, percentages, text and &.
Anything the explain AST cannot represent (booleans, ^, named ranges) raises
ValueError, so the caller records the formula as unverified instead of
guessing.
"""

from __future__ import annotations

import re

from archon.explain import formula_ast as ex
from archon.formula import ast as fa
from archon.formula.parser import parse

_SUPPORTED_OPS = frozenset({"+", "-", "*", "/", "&", "<", "<=", ">", ">=", "=", "<>"})
_CELL = re.compile(r"^[A-Z]{1,3}\d+$")


def _number(value: float) -> str:
    """Render a numeric literal the way it is usually written (1 not 1.0)."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _address(ref: fa.Ref) -> str:
    """A1 text of a single-cell ref, sheet-qualified when the formula names a sheet."""
    cell = ref.r1c1.replace("$", "").upper()
    if not _CELL.match(cell):
        raise ValueError(f"not a single-cell reference: {ref.r1c1!r}")
    return f"{ref.sheet}!{cell}" if ref.sheet else cell


def _convert(node: fa.Node) -> ex.Node:
    if isinstance(node, fa.Lit):
        if isinstance(node.value, str):
            return ex.Str(node.value)
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ValueError(f"unsupported literal: {node.value!r}")  # noqa: TRY004 - ValueError means "unverified" to callers
        return ex.Num(_number(node.value))
    if isinstance(node, fa.Ref):
        return ex.Ref(_address(node))
    if isinstance(node, fa.UnaryOp):
        inner = _convert(node.operand)
        if not isinstance(inner, ex.Num):
            raise ValueError("unary operator on a non-number")  # noqa: TRY004
        if node.op == "-" and not node.postfix:
            return ex.Num(inner.text[1:] if inner.text.startswith("-") else "-" + inner.text)
        if node.op == "%" and node.postfix:
            return ex.Num(_number(float(inner.text) / 100))
        raise ValueError(f"unsupported unary operator: {node.op!r}")
    if isinstance(node, fa.BinOp):
        if node.op == ":" and isinstance(node.left, fa.Ref) and isinstance(node.right, fa.Ref):
            start, end = _address(node.left), _address(node.right)
            return ex.Range(start, end.split("!")[-1])
        if node.op not in _SUPPORTED_OPS:
            raise ValueError(f"unsupported operator: {node.op!r}")
        return ex.BinOp(node.op, _convert(node.left), _convert(node.right))
    if isinstance(node, fa.Func):
        return ex.Call(node.name.upper(), tuple(_convert(a) for a in node.args))
    raise ValueError(f"unsupported node: {type(node).__name__}")


def explain_tree(formula: str) -> ex.Node:
    """Parse a formula for the matcher: the explain parser first (exact source
    text), then Senpai's full parser through the adapter. Raises ValueError
    (including formula.parser.ParseError) when neither can represent it.
    """
    try:
        return ex.parse_mock_formula(formula)
    except ValueError:
        return _convert(parse(formula))
