import json
from pathlib import Path
import openpyxl
from archon.ingest.xlsx import extract


def _make_fixture(path: Path) -> None:
    """Create a workbook with mixed content for determinism testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Revenue"
    ws["A1"] = "Sales"
    ws["B1"] = 100
    ws["C1"] = "=B1*2"
    ws["A2"] = "Tax"
    ws["B2"] = 20
    ws["C2"] = "=B2*0.1"
    wb.save(path)


def test_two_runs_produce_identical_output(tmp_path):
    """Two extractions of the same file must produce byte-identical JSON."""
    fixture = tmp_path / "determinism.xlsx"
    _make_fixture(fixture)

    result1 = extract(fixture)
    result2 = extract(fixture)

    json1 = json.dumps(
        result1.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    json2 = json.dumps(
        result2.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )

    # workbook_id is a uuid4 so exclude it from comparison
    data1 = result1.model_dump(mode="json")
    data2 = result2.model_dump(mode="json")
    data1.pop("workbook_id")
    data2.pop("workbook_id")

    json1 = json.dumps(data1, sort_keys=True, separators=(",", ":"))
    json2 = json.dumps(data2, sort_keys=True, separators=(",", ":"))

    assert json1 == json2, "Two runs produced different output"


def test_cells_are_sorted_by_sheet_row_col(tmp_path):
    """Cells must be sorted by (sheet, row, col) for deterministic output."""
    fixture = tmp_path / "determinism.xlsx"
    _make_fixture(fixture)

    result = extract(fixture)

    keys = [(c.sheet, c.row, c.col) for c in result.cells]
    assert keys == sorted(keys), "Cells are not sorted by (sheet, row, col)"


def test_sheets_are_sorted_by_index(tmp_path):
    """Sheets must be sorted by index for deterministic output."""
    fixture = tmp_path / "determinism.xlsx"
    _make_fixture(fixture)

    result = extract(fixture)

    indices = [s.index for s in result.sheets]
    assert indices == sorted(indices), "Sheets are not sorted by index"