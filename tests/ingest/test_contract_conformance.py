from pathlib import Path
from archon.contracts.extract import RawExtract
from archon.ingest.xlsx import extract

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xlsx"


def test_output_validates_as_contract_a():
    result = extract(FIXTURE)
    RawExtract.model_validate(result.model_dump())