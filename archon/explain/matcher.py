"""Deterministic structural matcher: formula AST -> ExplanationRecord.

Idioms live in patterns/*.yaml. Each pattern names a structural `shape`;
shapes are the only code. A new idiom of an existing shape is a data change.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from archon.contracts.explain import Evidence, ExplanationRecord
from archon.explain.formula_ast import (
    BinOp,
    Call,
    Node,
    Num,
    Range,
    Ref,
    prior_row_address,
    to_formula_text,
)
from archon.explain.lexicon import load_lexicon

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
    return tuple(sorted(specs, key=lambda spec: (spec.get("priority", 50), spec["id"])))


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


def _match_binary(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """Exactly two cell references joined by the pattern's operator."""
    if not (
        isinstance(tree, BinOp)
        and tree.op == spec["op"]
        and isinstance(tree.left, Ref)
        and isinstance(tree.right, Ref)
    ):
        return None
    first, second = spec["captures"]
    return {first: tree.left.address, second: tree.right.address}


def _arg_text(node: Node, kind: str) -> str | None:
    """Text of an argument if it has the wanted kind (ref, num, range)."""
    if kind == "ref" and isinstance(node, Ref):
        return node.address
    if kind == "num" and isinstance(node, Num):
        return node.text
    if kind == "int" and isinstance(node, Num) and node.text.isdigit():
        return node.text
    if kind == "expr":
        return to_formula_text(node)
    if kind == "leaf" and isinstance(node, Num | Ref):
        return to_formula_text(node)
    if kind == "range" and isinstance(node, Range):
        return f"{node.start}:{node.end}"
    return None


_RANGE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")


def _col_number(letters: str) -> int:
    """Spreadsheet column letters to a 1-based number (A=1, AA=27)."""
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def _range_dims(text: str) -> tuple[int, int] | None:
    """(rows, columns) of a range such as F1:H20, or None if unreadable."""
    found = _RANGE.match(text)
    if found is None:
        return None
    col1, row1, col2, row2 = found.groups()
    rows = abs(int(row2) - int(row1)) + 1
    cols = abs(_col_number(col2) - _col_number(col1)) + 1
    return rows, cols


def _column_in_table(captured: Captured) -> bool:
    """VLOOKUP's column index must lie within the table's width."""
    dims = _range_dims(captured["table"])
    return dims is not None and 1 <= int(captured["column"]) <= dims[1]


def _index_match_geometry(captured: Captured) -> bool:
    """INDEX-MATCH ranges must be single columns of equal height."""
    result = _range_dims(captured["result_range"])
    lookup = _range_dims(captured["lookup_range"])
    return (
        result is not None
        and lookup is not None
        and result[1] == 1
        and lookup[1] == 1
        and result[0] == lookup[0]
    )


VALIDATORS: dict[str, Callable[[Captured], bool]] = {
    "column_in_table": _column_in_table,
    "index_match_geometry": _index_match_geometry,
}


def _match_arg(node: Node, want: Spec) -> Captured | None:
    """Match one argument against its spec; return its captures or None."""
    kind = want["kind"]
    if kind == "call":
        return _match_call(node, "", want)
    if kind == "lit":
        if isinstance(node, Num) and node.text in want["values"]:
            return {want["as"]: want["values"][node.text]}
        return None
    text = _arg_text(node, kind)
    if text is None:
        return None
    return {want["as"]: text}


def _match_call(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """A call to one function whose arguments match the listed specs."""
    wanted = spec["args"]
    if not (
        isinstance(tree, Call)
        and tree.name == spec["function"]
        and len(tree.args) == len(wanted)
    ):
        return None
    captured: Captured = {}
    for arg, want in zip(tree.args, wanted, strict=True):
        part = _match_arg(arg, want)
        if part is None:
            return None
        captured.update(part)
    for name in spec.get("validate", []):
        if not VALIDATORS[name](captured):
            return None
    return captured


SHAPES: dict[str, Callable[[Node, str, Spec], Captured | None]] = {
    "if_ladder": _match_ladder,
    "additive_chain": _match_chain,
    "binary_refs": _match_binary,
    "call_args": _match_call,
}


def _render(spec: Spec, captured: Captured) -> str:
    """Fill the pattern's sentence template; empty optional clauses vanish."""
    context: dict[str, str] = dict(captured)
    for key, clause in sorted(spec.get("clauses", {}).items()):
        context[f"{key}_clause"] = clause.format(**captured) if captured[key] else ""
    return spec["template"].format(**context)


def match_formula(
    node_id: str,
    cell_address: str,
    tree: Node,
    header: str | None = None,
) -> ExplanationRecord:
    """Explain a formula, or return an unverified record. Never guesses."""
    res = load_lexicon().resolve(header) if header else None
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
                    header_resolved=res.resolved if res else False,
                    header_terms=list(res.terms) if res else [],
                ),
                confidence=1.0,
            )
    return ExplanationRecord(node_id=node_id, status="unverified", confidence=0.0)
