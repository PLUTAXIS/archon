"""A1 -> R1C1 formula conversion.

A formula dragged down 10,000 rows has 10,000 different A1 texts but exactly
one R1C1 text, so identical R1C1 text means "same cluster".

    to_r1c1("=B6*C6", "D6")  ->  "=RC[-2]*RC[-1]"
    to_r1c1("=B7*C7", "D7")  ->  "=RC[-2]*RC[-1]"

Public API:
    to_r1c1(formula, cell)  A1 formula plus its own address -> R1C1 text
    to_a1(formula, cell)    inverse, used for round-trip verification
"""

from __future__ import annotations

import re
from collections.abc import Callable

MAX_COL = 16384
MAX_ROW = 1048576


def col_to_num(letters: str) -> int:
    """Convert a column letter string (e.g. "C", "AB") to its 1-based column number."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n: int) -> str:
    """Convert a 1-based column number to its column letter string (e.g. 3 -> "C")."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def parse_address(addr: str) -> tuple[int, int]:
    """Parse a plain A1-style cell address (no sheet) into (row, column).

    Example: "D6" -> (6, 4). Dollar signs are accepted and ignored.
    Raises ValueError if the address is not a valid cell reference, or if
    the parsed row/column fall outside the real worksheet bounds
    (1..MAX_ROW, 1..MAX_COL) -- this rejects syntactically address-shaped
    but out-of-range text such as "A0" or "XFE1".
    """
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", addr.strip())
    if not m:
        raise ValueError(f"Bad cell address: {addr!r}")
    row = int(m.group(2))
    col = col_to_num(m.group(1))
    if row < 1 or row > MAX_ROW or col < 1 or col > MAX_COL:
        raise ValueError(f"Cell address out of worksheet bounds: {addr!r}")
    return row, col


_LITERAL = re.compile(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'')


def _map_code(formula: str, fn: Callable[[str], str]) -> str:
    """Apply fn to every part of formula that is not a quoted string literal.

    String literals ("...") and quoted sheet names ('...') are copied through
    unchanged so references inside them are never rewritten.
    """
    out: list[str] = []
    pos = 0
    for m in _LITERAL.finditer(formula):
        out.append(fn(formula[pos : m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(formula[pos:]))
    return "".join(out)


_A1 = re.compile(
    r"""
    (?P<cell>
        (?<![A-Za-z0-9_.$])
        (?P<cabs>\$?)(?P<ccol>[A-Za-z]{1,3})
        (?P<rabs>\$?)(?P<crow>\d+)
        (?![A-Za-z0-9_(!.]|:[A-Za-z0-9_.]+!)
    )
  | (?P<colrng>
        (?<![A-Za-z0-9_.$])
        (?P<c1abs>\$?)(?P<c1>[A-Za-z]{1,3}):(?P<c2abs>\$?)(?P<c2>[A-Za-z]{1,3})
        (?![A-Za-z0-9_(!.])
    )
  | (?P<rowrng>
        (?<![A-Za-z0-9_.$:])
        (?P<r1abs>\$?)(?P<r1>\d+):(?P<r2abs>\$?)(?P<r2>\d+)
        (?![A-Za-z0-9_.(:])
    )
""",
    re.VERBOSE,
)


def _row_part(abs_flag: str, row: int, cur_row: int) -> str:
    """Render the R-part of an R1C1 token: "R{row}" if absolute, else a relative offset."""
    if abs_flag:
        return f"R{row}"
    d = row - cur_row
    return "R" if d == 0 else f"R[{d}]"


def _col_part(abs_flag: str, col: int, cur_col: int) -> str:
    """Render the C-part of an R1C1 token: "C{col}" if absolute, else a relative offset."""
    if abs_flag:
        return f"C{col}"
    d = col - cur_col
    return "C" if d == 0 else f"C[{d}]"


def to_r1c1(formula: str, cell: str) -> str:
    """Convert an A1-style formula located at `cell` into relative R1C1 text.

    Identical dragged formulas (e.g. "=B6*C6" at D6 and "=B7*C7" at D7) produce
    the same R1C1 string, which is what makes clustering by text possible.
    Absolute references ($B$7) stay absolute in the R1C1 output.

    Known limitation: a separately-sheet-qualified range endpoint such as
    "Sheet1!A1:Sheet1!B1" is not currently distinguished from an unquoted 3D
    sheet range such as "Q1:Q3!A1", because this module works on formula
    text rather than a real parsed AST. Clustering of ordinary (non-3D,
    non-cross-sheet-range) formulas is unaffected. This will be resolved
    when R1C1 translation moves onto the AST produced by
    archon/formula/parser.py.
    """
    cur_row, cur_col = parse_address(cell)

    def convert(code: str) -> str:
        """Rewrite all non-literal reference tokens in one code segment."""

        def repl(m: re.Match[str]) -> str:
            """Render the matched A1 reference or range as R1C1 text."""
            if m.group("cell"):
                col = col_to_num(m.group("ccol"))
                row = int(m.group("crow"))
                if col > MAX_COL or row > MAX_ROW or row == 0:
                    return m.group(0)
                return _row_part(m.group("rabs"), row, cur_row) + _col_part(
                    m.group("cabs"), col, cur_col
                )
            if m.group("colrng"):
                c1 = col_to_num(m.group("c1"))
                c2 = col_to_num(m.group("c2"))
                if c1 > MAX_COL or c2 > MAX_COL:
                    return m.group(0)
                return (
                    _col_part(m.group("c1abs"), c1, cur_col)
                    + ":"
                    + _col_part(m.group("c2abs"), c2, cur_col)
                )
            r1 = int(m.group("r1"))
            r2 = int(m.group("r2"))
            if r1 == 0 or r2 == 0 or r1 > MAX_ROW or r2 > MAX_ROW:
                return m.group(0)
            return (
                _row_part(m.group("r1abs"), r1, cur_row)
                + ":"
                + _row_part(m.group("r2abs"), r2, cur_row)
            )

        return _A1.sub(repl, code)

    return _map_code(formula, convert)


# Three forms must be matched for the inverse conversion, because to_r1c1
# can emit each of them: a full "RxCy" token, a column-only token (from a
# whole-column range like "C[-1]"), and a row-only token (from a whole-row
# range like "R[-3]"). Each alternative is tried in order; the literal
# letters actually present in the matched text ("R" and/or "C") tell repl()
# which alternative fired, since Python's re module does not support
# reusing one group name across alternatives.
_R1C1 = re.compile(
    r"""
    (?<![A-Za-z0-9_.])
    (?:
        R(?P<rc_r>\[-?\d+\]|\d+)?C(?P<rc_c>\[-?\d+\]|\d+)?
      | C(?P<c_only>\[-?\d+\]|\d+)?
      | R(?P<r_only>\[-?\d+\]|\d+)?
    )
    (?![A-Za-z0-9_(])
""",
    re.VERBOSE,
)


def _axis(tok: str | None, cur: int, max_val: int) -> tuple[str, int] | None:
    """Resolve one R1C1 axis token to (abs_flag, numeric value).

    Returns None if the resolved value falls outside 1..max_val, so the
    caller can refuse to produce a malformed A1 reference (e.g. column 0).
    """
    if tok is None:
        value = cur
        abs_flag = ""
    elif tok.startswith("["):
        value = cur + int(tok[1:-1])
        abs_flag = ""
    else:
        value = int(tok)
        abs_flag = "$"
    if value < 1 or value > max_val:
        return None
    return abs_flag, value


def to_a1(formula: str, cell: str) -> str:
    """Convert an R1C1-style formula located at `cell` back into A1 text.

    This is the inverse of to_r1c1 and is used for round-trip verification,
    not as a primary output format. Handles full (RxCy), column-only, and
    row-only R1C1 tokens. A token that resolves outside the worksheet
    bounds (e.g. column 0) is left unchanged rather than producing a
    malformed A1 reference.
    """
    cur_row, cur_col = parse_address(cell)

    def convert(code: str) -> str:
        """Rewrite all R1C1 tokens in one code segment back to A1 text."""

        def repl(m: re.Match[str]) -> str:
            """Render the matched R1C1 token as A1 text."""
            text = m.group(0)
            # Determine which alternative matched from the literal letters present.
            if m.group("rc_r") is not None or m.group("rc_c") is not None or text.startswith("RC") or (text.startswith("R") and "C" in text):
                row_res = _axis(m.group("rc_r"), cur_row, MAX_ROW)
                col_res = _axis(m.group("rc_c"), cur_col, MAX_COL)
                if row_res is None or col_res is None:
                    return text
                rabs, row = row_res
                cabs, col = col_res
                return f"{cabs}{num_to_col(col)}{rabs}{row}"
            if text.startswith("C"):
                col_res = _axis(m.group("c_only"), cur_col, MAX_COL)
                if col_res is None:
                    return text
                cabs, col = col_res
                return f"{cabs}{num_to_col(col)}"
            if text.startswith("R"):
                row_res = _axis(m.group("r_only"), cur_row, MAX_ROW)
                if row_res is None:
                    return text
                rabs, row = row_res
                return f"{rabs}{row}"
            return text

        return _R1C1.sub(repl, code)

    return _map_code(formula, convert)


# --- AST-based R1C1 translation -------------------------------------------
#
# The functions above are the original, pre-parser, regex/string-based
# A1<->R1C1 text converter (still used by cluster/engine.py). The function
# below is the new AST-based translation path: given a parsed formula (see
# archon.formula.parser.parse) and the anchor cell the formula lives in, it
# walks the tree and rewrites every Ref node's r1c1 field from raw A1 text
# (what the parser currently stores there, see parser.py's module docstring)
# into real R1C1 notation. A defined name (a Ref whose text doesn't match a
# cell/column/row address shape) is left untouched, since it isn't a
# cell/range reference and has no R1C1 form -- this mirrors the parser's
# own documented gap rather than hiding it.
#
# A sheet-qualified range endpoint ("Sheet1!A1:Sheet1!B1") is handled
# correctly here, for real, because the parser already disambiguated it at
# parse time -- this was the long-standing regression the old text-based
# to_r1c1() could never fix without breaking "Q1:Q3!A1" (see that
# function's docstring).

from archon.formula.ast import BinOp, Func, Lit, Node, Ref, UnaryOp

_FULL_ADDR = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)(\d+)")
_COL_ONLY = re.compile(r"(\$?)([A-Za-z]{1,3})")
_ROW_ONLY = re.compile(r"(\$?)(\d+)")


def _parse_ref_corner(text: str) -> tuple[int | None, int | None, bool, bool]:
    """Parse one Ref node's raw A1 corner text into (row, col, row_abs, col_abs).

    row and/or col are None for a whole-column ("A") or whole-row ("1")
    reference. Returns (None, None, False, False) for text that isn't a
    cell/column/row address at all (a defined name) -- the caller leaves
    such a Ref unconverted.
    """
    m = _FULL_ADDR.fullmatch(text)
    if m:
        col_dollar, letters, row_dollar, digits = m.groups()
        return int(digits), col_to_num(letters), bool(row_dollar), bool(col_dollar)
    m = _COL_ONLY.fullmatch(text)
    if m:
        dollar, letters = m.groups()
        return None, col_to_num(letters), False, bool(dollar)
    m = _ROW_ONLY.fullmatch(text)
    if m:
        dollar, digits = m.groups()
        return int(digits), None, bool(dollar), False
    return None, None, False, False


def _r1c1_corner_text(text: str, anchor_row: int, anchor_col: int) -> str:
    """Translate one Ref node's raw A1 corner text into R1C1 text.

    Returns the original text unchanged if it isn't a recognizable
    cell/column/row address (a defined name) -- see module note above.
    """
    row, col, row_abs, col_abs = _parse_ref_corner(text)
    if row is None and col is None:
        return text

    row_part = ""
    if row is not None:
        if row_abs:
            row_part = f"R{row}"
        else:
            offset = row - anchor_row
            row_part = "R" if offset == 0 else f"R[{offset}]"

    col_part = ""
    if col is not None:
        if col_abs:
            col_part = f"C{col}"
        else:
            offset = col - anchor_col
            col_part = "C" if offset == 0 else f"C[{offset}]"

    return row_part + col_part


def _quote_sheet_if_needed(sheet: str) -> str:
    """Wrap a sheet name in single quotes if it needs them in formula text."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", sheet):
        return sheet
    return "'" + sheet.replace("'", "''") + "'"


def to_r1c1_ast(node: Node, anchor: tuple[int, int]) -> Node:
    """Rewrite every Ref node in an AST from raw A1 text to real R1C1 text.

    anchor is (row, col) of the cell the formula lives in, 1-based, as
    returned by parse_address(). Returns a new tree; the input is not
    mutated (all AST node types here are frozen dataclasses). A Ref that
    turns out to be a defined name (not a cell/column/row address) is
    passed through with its r1c1 field unchanged.
    """
    anchor_row, anchor_col = anchor

    if isinstance(node, Lit):
        return node

    if isinstance(node, Ref):
        new_text = _r1c1_corner_text(node.r1c1, anchor_row, anchor_col)
        return Ref(sheet=node.sheet, r1c1=new_text, absolute=node.absolute)

    if isinstance(node, UnaryOp):
        return UnaryOp(
            op=node.op,
            operand=to_r1c1_ast(node.operand, anchor),
            postfix=node.postfix,
        )

    if isinstance(node, BinOp):
        return BinOp(
            op=node.op,
            left=to_r1c1_ast(node.left, anchor),
            right=to_r1c1_ast(node.right, anchor),
        )

    if isinstance(node, Func):
        return Func(
            name=node.name,
            args=tuple(to_r1c1_ast(arg, anchor) for arg in node.args),
        )

    raise TypeError(f"Unknown AST node type: {type(node).__name__}")
