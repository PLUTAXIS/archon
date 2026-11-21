"""Business labels for cells, read from the workbook's own layout.

A column header is the nearest text cell above that has data directly below
it (so a title row above the header, or a column of names, is skipped). A row
label is the nearest text cell to the left with data directly to its right.
Dragged blocks are named by their column header; one-off cells (a summary
sheet's "Bonus pool") prefer their row label.

relabel() names every cell reference in an explanation, e.g. "A2" becomes
"Price (A2)". References with no label stay as they are; nothing is invented.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable

from archon.formula.r1c1 import parse_address

Row = tuple[str, str, str]
_ISO_MIDNIGHT = "T00:00:00"
_QUOTED = re.compile("(“[^”]*”)")
_REF = re.compile(
    r"(?<![\w$!.:'])"
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_][\w.]*)!)?"
    r"(?P<start>[A-Z]{1,3}\d+)(?::(?P<end>[A-Z]{1,3}\d+))?"
    r"(?![\w(!])"
)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


class Labels:
    """Index of text cells by column and by row, for header and label lookup."""

    def __init__(self, rows: Iterable[Row]) -> None:
        self._text: dict[tuple[str, int, int], str] = {}
        self._filled: set[tuple[str, int, int]] = set()
        by_col: defaultdict[tuple[str, int], list[int]] = defaultdict(list)
        by_row: defaultdict[tuple[str, int], list[int]] = defaultdict(list)
        for sheet, addr, content in rows:
            text = str(content).strip()
            if not text:
                continue
            row, col = parse_address(addr)
            self._filled.add((sheet, row, col))
            if text.startswith("=") or _is_number(text):
                continue
            self._text[(sheet, row, col)] = text.lstrip("'").removesuffix(_ISO_MIDNIGHT)
            by_col[(sheet, col)].append(row)
            by_row[(sheet, row)].append(col)
        self._col_index = {k: sorted(v) for k, v in by_col.items()}
        self._row_index = {k: sorted(v) for k, v in by_row.items()}
        # A header row has at least one text cell with data directly below it;
        # every text cell in that row is then a header (even over a text column).
        self._header_rows = {
            (sheet, row) for (sheet, row, col) in self._text if self._is_data(sheet, row + 1, col)
        }

    def _is_data(self, sheet: str, row: int, col: int) -> bool:
        return (sheet, row, col) in self._filled and (sheet, row, col) not in self._text

    def column(self, sheet: str, row: int, col: int) -> str | None:
        """Nearest text above (sheet, row, col) that sits in a header row."""
        rows = self._col_index.get((sheet, col), [])
        for r in reversed(rows[: bisect_left(rows, row)]):
            if (sheet, r) in self._header_rows:
                return self._text[(sheet, r, col)]
        return None

    def row(self, sheet: str, row: int, col: int) -> str | None:
        """Nearest text left of (sheet, row, col) with data directly to its right."""
        cols = self._row_index.get((sheet, row), [])
        for c in reversed(cols[: bisect_left(cols, col)]):
            if self._is_data(sheet, row, c + 1):
                return self._text[(sheet, row, c)]
        return None

    def cell(self, sheet: str, addr: str, *, prefer_row: bool) -> str | None:
        row, col = parse_address(addr)
        if prefer_row:
            return self.row(sheet, row, col) or self.column(sheet, row, col)
        return self.column(sheet, row, col)

    def relabel(self, text: str, home_sheet: str, *, prefer_row: bool) -> str:
        """Name every cell reference in text: 'A2' -> 'Price (A2)'."""

        def name(m: re.Match[str]) -> str:
            sheet = (m["sheet"] or home_sheet).strip("'").replace("''", "'")
            start, end = m["start"], m["end"]
            if end:
                same_col = start.rstrip("0123456789") == end.rstrip("0123456789")
                label = self.cell(sheet, start, prefer_row=False) if same_col else None
            else:
                label = self.cell(sheet, start, prefer_row=prefer_row)
            return f"{label} ({m[0]})" if label else m[0]

        # text the formula quotes (“A1”) is a literal, not a cell: leave it untouched
        parts = _QUOTED.split(text)
        return "".join(p if i % 2 else _REF.sub(name, p) for i, p in enumerate(parts))

