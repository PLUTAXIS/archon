import json
from pathlib import Path

import pytest

from archon.contracts.extract import RawExtract

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_files():
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_validates(fixture_path):
    data = json.loads(fixture_path.read_text())
    RawExtract.model_validate(data)