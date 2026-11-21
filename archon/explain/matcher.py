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
    Str,
    parse_mock_formula,
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
_WHOLE_COLUMNS = re.compile(r"^([A-Z]+):([A-Z]+)$")
_SHEET_ROWS = 1_048_576  # a whole column spans every row of the sheet


def _col_number(letters: str) -> int:
    """Spreadsheet column letters to a 1-based number (A=1, AA=27)."""
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def _range_dims(text: str) -> tuple[int, int] | None:
    """(rows, columns) of F1:H20, Inputs!F1:H20 or whole columns F:H; None if unreadable."""
    text = text.rsplit("!", 1)[-1]
    whole = _WHOLE_COLUMNS.match(text)
    if whole:
        return _SHEET_ROWS, abs(_col_number(whole[2]) - _col_number(whole[1])) + 1
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
    if kind == "expr":
        # Record idioms and typed-in numbers inside the expression, so an
        # approximate lookup hidden in IFERROR(...) still counts toward risk.
        embedded: list[str] = []
        constants: list[str] = []
        if _phrase(node, embedded, constants) is not None:
            if constants:
                embedded.append("arithmetic_constant")
            if embedded:
                return {want["as"]: text, "embedded": ",".join(embedded)}
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


_ARITH_WORDS = {"+": "plus", "-": "minus", "*": "multiplied by", "/": "divided by", "&": "followed by"}
_COMPARE_WORDS = {
    ">": "is greater than", "<": "is less than", ">=": "is at least",
    "<=": "is at most", "=": "equals", "<>": "does not equal",
}
FUNCTIONS_FILE = Path(__file__).parent / "functions.yaml"
_POSITIONAL = re.compile(r"\{(\d+)\}")


@lru_cache(maxsize=1)
def load_functions() -> dict[str, Spec]:
    """functions.yaml, each entry normalised to {phrase, arity, structural, conditions}."""
    raw = yaml.safe_load(FUNCTIONS_FILE.read_text(encoding="utf-8"))["functions"]
    out: dict[str, Spec] = {}
    for name, entry in raw.items():
        spec = {"phrase": entry} if isinstance(entry, str) else dict(entry)
        positions = [int(i) for i in _POSITIONAL.findall(spec["phrase"])]
        spec["arity"] = max(positions) + 1 if positions else None
        spec["structural"] = frozenset(spec.get("structural", ()))
        spec["conditions"] = bool(spec.get("conditions", False))
        out[name] = spec
    return out


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _phrase_function(node: Call, embedded: list[str], constants: list[str]) -> str | None:
    """IF(...) or a function listed in functions.yaml, read aloud."""
    if node.name == "IF" and len(node.args) in (2, 3):
        parts = [
            _phrase(arg, embedded, constants, condition=(i == 0)) for i, arg in enumerate(node.args)
        ]
        if any(p is None for p in parts):
            return None
        # bracket an IF nested in a branch so the reader can tell the levels apart
        parts = [
            f"({p})" if i and isinstance(a, Call) and a.name == "IF" else p
            for i, (p, a) in enumerate(zip(parts, node.args, strict=True))
        ]
        text = f"if {parts[0]}, {parts[1]}"
        return f"{text}; otherwise {parts[2]}" if len(parts) == 3 else text
    spec = load_functions().get(node.name)
    if spec is None or not node.args or spec["arity"] not in (None, len(node.args)):
        return None
    args = []
    for i, arg in enumerate(node.args):
        # settings (decimals, character counts) must be whole numbers: Excel
        # silently truncates ROUND(A1,1.5), so "1.5 decimal places" would mislead
        if i in spec["structural"] and isinstance(arg, Num) and not arg.text.isdigit():
            return None
        found: list[str] = [] if i in spec["structural"] else constants  # settings, not business values
        text = _phrase(arg, embedded, found, condition=spec["conditions"])
        if text is None:
            return None
        # "(A1 multiplied by B1) rounded to 2", not "A1 multiplied by B1 rounded to 2"
        args.append(f"({text})" if isinstance(arg, BinOp) and not spec["conditions"] else text)
    if spec["arity"] is None:
        return str(spec["phrase"]).format(args=_join(args))
    return str(spec["phrase"]).format(*args)


# Numbers that are structure, not business assumptions (x*1, 1-rate, /100).
_TRIVIAL_NUMBERS = frozenset({"0", "1", "100"})


def _phrase(
    node: Node, embedded: list[str], constants: list[str], *, condition: bool = False
) -> str | None:
    """Read a formula tree aloud, exactly; None if any part is not representable.

    Functions are read only through a call_args pattern `phrase`, IF, or an
    entry in functions.yaml, so nothing is paraphrased that can't be verified.
    Comparisons are read only where a condition is expected (IF, AND, OR).
    Text is wrapped in curly quotes so cell names inside it are never relabelled.
    """
    if isinstance(node, Num):
        if node.text.lstrip("-") not in _TRIVIAL_NUMBERS:
            constants.append(node.text)
        return node.text
    if isinstance(node, Ref):
        return node.address
    if isinstance(node, Range):
        return f"{node.start}:{node.end}"  # whole columns stay as written: C:C
    if isinstance(node, Str):
        return f"“{node.text}”"
    if isinstance(node, BinOp):
        word = _ARITH_WORDS.get(node.op) or (_COMPARE_WORDS.get(node.op) if condition else None)
        if word is None:
            return None
        sides = []
        for side in (node.left, node.right):
            text = _phrase(side, embedded, constants)
            if text is None:
                return None
            sides.append(f"({text})" if isinstance(side, BinOp) else text)
        return f"{sides[0]} {word} {sides[1]}"
    if isinstance(node, Call):
        for spec in load_patterns():
            if "phrase" in spec and spec["shape"] == "call_args":
                captured = _match_call(node, "", spec)
                if captured is not None:
                    embedded.append(spec["id"])
                    return str(spec["phrase"]).format(**captured)
        return _phrase_function(node, embedded, constants)
    return None


def _match_arithmetic(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """Any + - * / expression of refs, numbers and known functions, read aloud.

    spec["constants"] selects formulas with (true) or without (false) a
    non-trivial number typed into them, so each gets its own risk flag.
    """
    if not (isinstance(tree, BinOp) and tree.op in _ARITH_WORDS):
        return None
    embedded: list[str] = []
    constants: list[str] = []
    expression = _phrase(tree, embedded, constants)
    if expression is None or bool(constants) != spec["constants"]:
        return None
    return {
        "expression": expression,
        "constants": ", ".join(constants),
        "embedded": ",".join(embedded),
    }


def _match_phrase_call(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """A function call (IF, AVERAGE, LEFT...) read aloud as a whole sentence."""
    if not isinstance(tree, Call):
        return None
    embedded: list[str] = []
    constants: list[str] = []
    expression = _phrase(tree, embedded, constants)
    if expression is None or bool(constants) != spec["constants"]:
        return None
    return {
        "expression": expression[0].upper() + expression[1:],
        "constants": ", ".join(constants),
        "embedded": ",".join(embedded),
    }


def _match_single_ref(tree: Node, _cell: str, spec: Spec) -> Captured | None:
    """The formula is just a link to one cell (=Inputs!B2)."""
    return {spec["captures"][0]: tree.address} if isinstance(tree, Ref) else None


SHAPES: dict[str, Callable[[Node, str, Spec], Captured | None]] = {
    "if_ladder": _match_ladder,
    "additive_chain": _match_chain,
    "binary_refs": _match_binary,
    "call_args": _match_call,
    "arithmetic": _match_arithmetic,
    "single_ref": _match_single_ref,
    "phrase_call": _match_phrase_call,
}


def _spoken(formula_text: str) -> str:
    """Formula text read aloud ("B2/C2" -> "B2 divided by C2") when exact, else as is."""
    try:
        return _phrase(parse_mock_formula(formula_text), [], []) or formula_text
    except ValueError:
        return formula_text


def _render(spec: Spec, captured: Captured) -> str:
    """Fill the pattern's sentence template; empty optional clauses vanish.

    Captures listed under `speak` are read aloud in the sentence only; the
    evidence keeps the exact formula text.
    """
    context: dict[str, str] = dict(captured)
    for key in spec.get("speak", []):
        context[key] = _spoken(captured[key])
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
