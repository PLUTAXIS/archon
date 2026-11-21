"""Severity's outlier check on a workbook calculated and saved by real Excel.

The fixture was built with openpyxl, then opened, recalculated and saved by Excel,
so it carries the cached results Excel writes. C8 is typed over with 999999 next to
formulas giving tens; C15 holds 160 where the formula would give 150 (plausible).
"""

from pathlib import Path

from archon.ingest.xlsx import extract
from archon.pipeline import run_extract

FIXTURE = Path(__file__).parent / "ingest" / "fixtures" / "excel_saved_override.xlsx"


def test_outlier_uses_the_value_excel_cached_next_to_it():
    bugs = {b["address"]: b for b in run_extract(extract(FIXTURE))["bugs"]}
    assert "typed value 999999 is far from the 70 the formula in C7 produced" in bugs["C8"]["severity_reasons"]
    assert bugs["C8"]["severity"] == 3
    assert bugs["C15"]["severity_reasons"] == ["feeds 1 other cell"]  # 160 vs 140: plausible
