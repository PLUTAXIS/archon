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
    Raises ValueError if the address is not a valid cell reference.
    """
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", addr.strip())
    if not m:
        raise ValueError(f"Bad cell address: {addr!r}")
    return int(m.group(2)), col_to_num(m.group(1))


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
        (?![A-Za-z0-9_(!.])
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
    """
    cur_row, cur_col = parse_address(cell)

    def convert(code: str) -> str:
        def repl(m: re.Match[str]) -> str:
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


_R1C1 = re.compile(
    r"""
    (?<![A-Za-z0-9_.])
    R(?P<r>\[-?\d+\]|\d+)?
    C(?P<c>\[-?\d+\]|\d+)?
    (?![A-Za-z0-9_(])
""",
    re.VERBOSE,
)


def _axis(tok: str | None, cur: int, to_text: Callable[[int], str]) -> tuple[str, str]:
    """Resolve one R1C1 axis token (e.g. "[-2]", "7", or None) to an (abs_flag, text) pair."""
    if tok is None:
        return "", to_text(cur)
    if tok.startswith("["):
        return "", to_text(cur + int(tok[1:-1]))
    return "$", to_text(int(tok))


def to_a1(formula: str, cell: str) -> str:
    """Convert an R1C1-style formula located at `cell` back into A1 text.

    This is the inverse of to_r1c1 and is used for round-trip verification,
    not as a primary output format.
    """
    cur_row, cur_col = parse_address(cell)

    def convert(code: str) -> str:
        def repl(m: re.Match[str]) -> str:
            rabs, row = _axis(m.group("r"), cur_row, str)
            cabs, col = _axis(m.group("c"), cur_col, num_to_col)
            return f"{cabs}{col}{rabs}{row}"

        return _R1C1.sub(repl, code)

    return _map_code(formula, convert)
