from pathlib import Path
import openpyxl
from archon.contracts.extract import RawExtract
from archon.ingest.xlsx import extract


def _make_fixture(path: Path) -> None:
    """Create a minimal xlsx fixture at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "hello"
    ws["B1"] = 42
    wb.save(path)


def test_output_validates_as_contract_a(tmp_path):
    """Extract a minimal xlsx and confirm the result validates as Contract A."""
    fixture = tmp_path / "minimal.xlsx"
    _make_fixture(fixture)
    result = extract(fixture)
    RawExtract.model_validate(result.model_dump())