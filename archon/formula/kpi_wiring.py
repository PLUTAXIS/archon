"""Wire the parse KPI into the real parse loop.

Contract: every formula cell goes through audit_formulas(). Parsed cells
proceed normally; failed cells are returned separately so the caller can
route them to the unverified appendix. Nothing is silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass

from archon.formula.parser import ParseError, parse
from archon.parser.kpi import ParseKPI


@dataclass(frozen=True)
class Cell:
    ref: str          # e.g. "Sheet1!B7"
    formula: str      # e.g. "=SUM(A1:A5)"


@dataclass(frozen=True)
class AuditResult:
    parsed: tuple[Cell, ...]
    failed: tuple[Cell, ...]   # route these to the unverified appendix
    kpi: ParseKPI


def audit_formulas(cells: list[Cell], source: str) -> AuditResult:
    kpi = ParseKPI(source=source)
    parsed: list[Cell] = []
    failed: list[Cell] = []
    for cell in cells:
        try:
            parse(cell.formula)
        except ParseError as exc:
            kpi.record_failed(cell.ref, cell.formula, str(exc))
            failed.append(cell)
        else:
            kpi.record_parsed(cell.ref)
            parsed.append(cell)
    return AuditResult(tuple(parsed), tuple(failed), kpi)
