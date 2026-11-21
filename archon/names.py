"""Named ranges and whole-column references, made visible to the analysis.

Excel formulas often say =Amount*TaxRate or =SUM(C:C). The graph builder only
understands A1 references, so without this a named input or a whole-column
total silently has no dependencies.

    table = reference_names(raw.defined_names, sheet_names)
    expand_names("=A2*TaxRate", "Calc", table)        -> "=A2*Inputs!$B$1"
    bound_whole_columns("=SUM(C:C)", "Calc", {"Calc": 500}) -> "=SUM(C1:C500)"

Only names that point at plain cells or ranges are expanded. A name holding a
constant (VAT = 0.2) or a formula (OFFSET...) is left alone, so the formula
stays unverified rather than being guessed at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from archon.contracts.extract import DefinedName

WORKBOOK = ""  # scope key for workbook-wide names
_SHEET = r"(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)"
_CELL = r"\$?[A-Z]{1,3}\$?\d+"
_COL = r"\$?[A-Z]{1,3}"
_PLAIN_REF = re.compile(rf"^={{0,1}}{_SHEET}!(?:{_CELL}(?::{_CELL})?|{_COL}:{_COL})$")
_STRING = re.compile(r'("(?:[^"]|"")*")')
_NAME_TOKEN = re.compile(r"(?<![\w.$!'\]])([A-Za-z_\\][\w.\\]*)(?![\w.(!\[])")
_WHOLE_COLUMN = re.compile(rf"(?<![\w$!.:'])(?:(?P<sheet>{_SHEET})!)?(?P<a>{_COL}):(?P<b>{_COL})(?![\w(!:])")

Table = Mapping[str, Mapping[str, tuple[str, str]]]  # scope -> NAME -> (name as written, reference)


def reference_names(
    names: Iterable[DefinedName], sheet_names: Sequence[str]
) -> dict[str, dict[str, tuple[str, str]]]:
    """{scope: {NAME: reference}} for names that refer to plain cells or ranges.

    scope is "" for workbook names, else the sheet name (Excel stores a
    sheet-scoped name with the sheet's index). Names are case-insensitive.
    """
    table: dict[str, dict[str, tuple[str, str]]] = {}
    for dn in names:
        ref = dn.refers_to.strip().removeprefix("=")
        if not _PLAIN_REF.match(ref):
            continue
        if dn.scope == "workbook":
            scope = WORKBOOK
        elif dn.scope.isdigit() and int(dn.scope) < len(sheet_names):
            scope = sheet_names[int(dn.scope)]
        else:
            continue
        table.setdefault(scope, {})[dn.name.upper()] = (dn.name, ref)
    return table


def _outside_strings(formula: str, fix) -> str:
    """Apply fix() to the parts of a formula that are not "text literals"."""
    parts = _STRING.split(formula)
    return "".join(p if i % 2 else fix(p) for i, p in enumerate(parts))


def expand_names(formula: str, sheet: str, table: Table) -> str:
    """Replace each name with the reference it stands for (sheet scope first)."""
    if not formula.startswith("=") or not table:
        return formula
    local, glob = table.get(sheet, {}), table.get(WORKBOOK, {})

    def swap(m: re.Match[str]) -> str:
        found = local.get(m[1].upper()) or glob.get(m[1].upper())
        return found[1] if found else m[1]

    return _outside_strings(formula, lambda part: _NAME_TOKEN.sub(swap, part))


def bound_whole_columns(formula: str, home_sheet: str, last_row: Mapping[str, int]) -> str:
    """A:A -> A1:A<last used row of that sheet>, so the graph can follow it.

    A sheet with no cells keeps the reference as is (nothing to depend on).
    """
    if not formula.startswith("=") or ":" not in formula:
        return formula

    def bound(m: re.Match[str]) -> str:
        sheet = (m["sheet"] or home_sheet).strip("'").replace("''", "'")
        rows = last_row.get(sheet)
        if not rows:
            return m[0]
        prefix = f"{m['sheet']}!" if m["sheet"] else ""
        return f"{prefix}{m['a']}1:{m['b']}{rows}"

    return _outside_strings(formula, lambda part: _WHOLE_COLUMN.sub(bound, part))


def named_cells(table: Table) -> dict[tuple[str, str], str]:
    """(sheet, A1 address or range) -> name, for labelling explanations."""
    out: dict[tuple[str, str], str] = {}
    for names in table.values():
        for name, ref in sorted(names.values()):
            sheet, _, addr = ref.rpartition("!")
            key = (sheet.strip("'").replace("''", "'"), addr.replace("$", ""))
            out.setdefault(key, name)
    return out
