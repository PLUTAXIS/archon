from pathlib import Path
import openpyxl
from archon.contracts.extract import RawExtract
from archon.ingest.xlsx import extract

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xlsx"


def _make_fixture() -> None:
    """Create a minimal xlsx fixture if it does not exist."""
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "hello"
    ws["B1"] = 42
    wb.save(FIXTURE)


def test_output_validates_as_contract_a():
    if not FIXTURE.exists():
        _make_fixture()
    result = extract(FIXTURE)
    RawExtract.model_validate(result.model_dump())