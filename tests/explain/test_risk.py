"""Risk score: pure, integer, attributed, sorted, capped."""

import json

from archon.contracts.graph import Risk
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import load_patterns, match_formula
from archon.explain.risk import (
    MAX_SCORE,
    RiskComponent,
    RiskResult,
    build_result,
    explicit_rule_ids,
    format_components,
    score_record,
    to_contract_risk,
)

LADDER = "=IF(B2<1000,0.05,IF(B2<5000,0.08,IF(B2<10000,0.12,0.15)))"


def _score(formula: str, cell: str = "G2") -> RiskResult:
    record = match_formula("n1", cell, parse_mock_formula(formula))
    return score_record(record)


def test_no_risk_idiom() -> None:
    r = _score("=E2*F2")
    assert (r.score, r.flags, r.components) == (0, (), ())


def test_volatile() -> None:
    r = _score("=NOW()")
    assert r.score == 15
    assert r.flags == ("VOLATILE_FUNCTION",)


def test_error_suppression() -> None:
    r = _score("=IFERROR(B2/C2,0)")
    assert r.score == 15
    assert r.flags == ("ERROR_SUPPRESSED",)


def test_tiered_depth() -> None:
    r = _score(LADDER)
    assert r.score == 15
    assert r.flags == ("NESTED_IF_DEPTH_3",)


def test_running_balance() -> None:
    r = _score("=D1+B2-C2", cell="D2")
    assert r.score == 5
    assert r.flags == ("RUNNING_BALANCE",)


def test_unverified() -> None:
    r = _score("=MEDIAN(A1:A10)")
    assert r.score == 20
    assert r.flags == ("UNVERIFIED_FORMULA",)


def test_components_sum_to_score() -> None:
    r = _score(LADDER)
    assert sum(c.points for c in r.components) == r.score


def test_cap() -> None:
    r = build_result(
        [RiskComponent("A", 60), RiskComponent("B", 60)]
    )
    assert r.score == MAX_SCORE == 100


def test_sorted_and_unique() -> None:
    r = build_result(
        [
            RiskComponent("VOLATILE_FUNCTION", 15),
            RiskComponent("ERROR_SUPPRESSED", 15),
            RiskComponent("ERROR_SUPPRESSED", 15),
        ]
    )
    assert r.flags == ("ERROR_SUPPRESSED", "VOLATILE_FUNCTION")


def test_format_components_exact() -> None:
    r = build_result(
        [
            RiskComponent("VOLATILE_FUNCTION", 15),
            RiskComponent("ERROR_SUPPRESSED", 15),
        ]
    )
    assert format_components(r) == (
        "ERROR_SUPPRESSED +15\nVOLATILE_FUNCTION +15\nTOTAL 30"
    )
    assert format_components(build_result([])) == "TOTAL 0"


def test_contract_adapter_round_trip() -> None:
    risk = to_contract_risk(_score(LADDER))
    assert isinstance(risk, Risk)
    assert risk.score == 15
    assert risk.flags == ["NESTED_IF_DEPTH_3"]
    assert Risk.model_validate_json(risk.model_dump_json()) == risk


def test_every_pattern_has_a_rule() -> None:
    ruled = set(explicit_rule_ids())
    missing = [s["id"] for s in load_patterns() if s["id"] not in ruled]
    assert missing == []


def test_determinism() -> None:
    first = _score(LADDER)
    first_json = to_contract_risk(first).model_dump_json()
    for _ in range(20):
        again = _score(LADDER)
        assert again == first
        assert to_contract_risk(again).model_dump_json() == first_json
    json.loads(first_json)


def test_lookup_risk_flags() -> None:
    cases = {
        "=VLOOKUP(A2,F1:H20,3)": (25, ("APPROX_LOOKUP_DEFAULT",)),
        "=VLOOKUP(A2,F1:H20,3,1)": (10, ("APPROX_LOOKUP",)),
        "=VLOOKUP(A2,F1:H20,3,0)": (0, ()),
        "=INDEX(C1:C20,MATCH(A2,B1:B20,0))": (0, ()),
    }
    for formula, (score, flags) in cases.items():
        r = _score(formula, cell="D2")
        assert (r.score, r.flags) == (score, flags)
