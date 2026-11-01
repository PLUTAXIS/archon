import json
import pathlib

import pytest
from pydantic import ValidationError

from archon.contracts.explain import ExplanationRecord
from archon.contracts.graph import DagGraph
from archon.contracts.parity import ParityCertificate

FIX = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_duplicate_node_ids_rejected():
    data = _load("dag_graph_minimal.json")
    data["nodes"].append(dict(data["nodes"][0]))
    with pytest.raises(ValidationError, match="duplicate node id"):
        DagGraph.model_validate(data)


def test_match_rate_contradicting_counts_rejected():
    data = _load("parity_certificate_minimal.json")
    data["cases_total"] = 100
    data["cases_passed"] = 99
    data["match_rate"] = "100.00"
    with pytest.raises(ValidationError, match="match_rate"):
        ParityCertificate.model_validate(data)


def test_zero_cases_rejected():
    data = _load("parity_certificate_minimal.json")
    data["cases_total"] = 0
    data["cases_passed"] = 0
    data["match_rate"] = "100.00"
    with pytest.raises(ValidationError, match="cases_total"):
        ParityCertificate.model_validate(data)


def test_unverified_with_idiom_rejected():
    data = _load("explanation_unverified_minimal.json")
    data["idiom"] = "running_balance"
    with pytest.raises(ValidationError, match="unverified"):
        ExplanationRecord.model_validate(data)


def test_matched_without_idiom_rejected():
    data = _load("explanation_matched_minimal.json")
    data["idiom"] = None
    with pytest.raises(ValidationError, match="idiom"):
        ExplanationRecord.model_validate(data)


def test_match_rate_ignores_decimal_context() -> None:
    """1 of 6 is 16.67 even when the caller lowers decimal precision."""
    import decimal

    data = _load("parity_certificate_minimal.json")
    data["cases_total"] = 6
    data["cases_passed"] = 1
    data["match_rate"] = "16.67"
    data["case_results"] = []
    with decimal.localcontext() as ctx:
        ctx.prec = 3
        ParityCertificate.model_validate(data)


def test_match_rate_rounds_half_up() -> None:
    """1 of 8 is exactly 12.5 and 1 of 16 is exactly 6.25; 1 of 32 is 3.125 -> 3.13."""
    data = _load("parity_certificate_minimal.json")
    data["case_results"] = []
    data["cases_total"], data["cases_passed"], data["match_rate"] = 32, 1, "3.13"
    ParityCertificate.model_validate(data)
