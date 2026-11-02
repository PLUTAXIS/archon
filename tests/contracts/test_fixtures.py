import json
from pathlib import Path

import pytest

from archon.contracts.bugs import BugLedgerEntry
from archon.contracts.explain import ExplanationRecord
from archon.contracts.extract import RawExtract
from archon.contracts.graph import DagGraph
from archon.contracts.parity import ParityCertificate
from archon.contracts.report import ReportDocument

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Maps a fixture filename prefix to the Pydantic model that should validate it.
# Checked in order; the first matching prefix wins.
PREFIX_TO_MODEL = [
    ("dag_graph", DagGraph),
    ("bug_ledger", BugLedgerEntry),
    ("parity_certificate", ParityCertificate),
    ("report_document", ReportDocument),
    ("explanation_matched", ExplanationRecord),
    ("explanation_unverified", ExplanationRecord),
    ("minimal_valid", RawExtract),
]


def _fixture_files():
    """Return all fixture JSON files, or an empty list if the fixtures directory is missing."""
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.json"))


def _model_for(fixture_path: Path):
    """Resolve the Pydantic model that should validate this fixture, by filename prefix."""
    for prefix, model in PREFIX_TO_MODEL:
        if fixture_path.stem.startswith(prefix):
            return model
    raise ValueError(f"No model mapping found for fixture file: {fixture_path.name}")


@pytest.mark.parametrize("fixture_path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_validates(fixture_path):
    data = json.loads(fixture_path.read_text())
    model = _model_for(fixture_path)
    model.model_validate(data)
