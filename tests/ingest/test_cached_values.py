from pathlib import Path
import openpyxl
from archon.ingest.xlsx import extract


def _make_value_fixture(path: Path) -> None:
    """Create a workbook with plain value cells."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = 10
    ws["B1"] = 20
    ws["C1"] = 30
    wb.save(path)


def _make_formula_fixture(path: Path) -> None:
    """Create a workbook with a formula cell saved by openpyxl.
    
    Note: openpyxl-created files have no cached values since Excel
    never ran the calculation. cached_value will be None for these cells.
    Real client files saved by Excel will have cached values populated.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = 10
    ws["B1"] = 20
    ws["C1"] = "=A1+B1"
    wb.save(path)


def test_non_formula_cells_have_cached_value(tmp_path):
    """Non-formula cells must have a cached value and no formula."""
    fixture = tmp_path / "values.xlsx"
    _make_value_fixture(fixture)
    result = extract(fixture)

    value_cells = [c for c in result.cells if c.formula is None]
    assert len(value_cells) > 0, "No value cells found"

    for cell in value_cells:
        assert cell.cached_value is not None, \
            f"Cell {cell.address} has no cached_value"


def test_formula_cells_have_formula_string(tmp_path):
    """Formula cells must carry a formula string starting with =."""
    fixture = tmp_path / "formulas.xlsx"
    _make_formula_fixture(fixture)
    result = extract(fixture)

    formula_cells = [c for c in result.cells if c.formula is not None]
    assert len(formula_cells) > 0, "No formula cells found"

    for cell in formula_cells:
        assert cell.formula.startswith("="), \
            f"Formula {cell.formula} missing leading ="


def test_formula_cached_value_from_excel_saved_file(tmp_path):
    """Formula cells in a file saved by Excel have both formula and cached value.
    
    Uses dragged_10k.xlsx which was saved by Excel and has real cached values.
    """
    fixture = Path("tests/ingest/fixtures/dragged_10k.xlsx")
    if not fixture.exists():
        return  # skip if fixture not available

    result = extract(fixture)
    formula_cells = [c for c in result.cells if c.formula is not None]
    assert len(formula_cells) > 0, "No formula cells found"

    # At least some formula cells should have cached values
    with_cached = [c for c in formula_cells if c.cached_value is not None]
    assert len(with_cached) > 0, \
        "No formula cells have cached values in Excel-saved file"