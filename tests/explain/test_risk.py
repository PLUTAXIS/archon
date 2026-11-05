"""Risk-score tests. Weights per handoff v2, Task 5 (proposed, pending Wrik)."""

from __future__ import annotations

from collections.abc import Mapping

from archon.contracts.graph import Risk
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import load_patterns, match_formula
from archon.explain.risk import (
    RiskResult,
    format_components,
    load_rules,
    pattern_flags,
    score_record,
    to_contract_risk,
)

NODE_ID = "Sheet1!R1C1#c1"


def _record(formula: str, cell: str = "A1"):
    return match_formula(NODE_ID, cell, parse_mock_formula(formula))


def test_no_risk_idiom_scores_zero():
    result = score_record(_record("=E2*F2", "G2"))
    assert result == RiskResult(score=0, flags=(), components=())


def test_volatile():
    result = score_record(_record("=NOW()"))
    assert result.score == 15
    assert result.flags == ("VOLATILE_FUNCTION",)


def test_error_suppression():
    result = score_record(_record("=IFERROR(B2/C2,0)", "D2"))
    assert result.score == 15
    assert result.flags == ("ERROR_SUPPRESSED",)


def test_approx_lookup_default():
    result = score_record(_record("=VLOOKUP(A2,F1:H20,3)", "D2"))
    assert result.score == 25
    assert result.flags == ("APPROX_LOOKUP_DEFAULT",)


def test_approx_lookup_explicit():
    result = score_record(_record("=VLOOKUP(A2,F1:H20,3,1)", "D2"))
    assert result.score == 10
    assert result.flags == ("APPROX_LOOKUP",)


def test_exact_lookup_scores_zero():
    result = score_record(_record("=VLOOKUP(A2,F1:H20,3,0)", "D2"))
    assert result == RiskResult(score=0, flags=(), components=())


def test_tiered_rate_table_depth():
    formula = "=IF(B2<1000,0.05,IF(B2<5000,0.08,IF(B2<10000,0.12,0.15)))"
    result = score_record(_record(formula, "C2"))
    assert result.flags == ("NESTED_IF_DEPTH_3",)
    assert result.score == 15


def test_running_balance():
    result = score_record(_record("=D1+B2-C2", "D2"))
    assert result.score == 5
    assert result.flags == ("RUNNING_BALANCE",)


def test_unverified_is_risk():
    result = score_record(_record("=MEDIAN(A1:A10)"))
    assert result.score == 20
    assert result.flags == ("UNVERIFIED_FORMULA",)


def test_components_sum_to_score():
    result = score_record(_record("=NOW()"))
    assert sum(c.points for c in result.components) == result.score
    assert result.components[0].flag == "VOLATILE_FUNCTION"


def test_score_capped_at_100():
    rules: Mapping[str, int] = {"VOLATILE_FUNCTION": 250, "NESTED_IF_DEPTH": 5}
    result = score_record(_record("=NOW()"), rules=rules)
    assert result.score == 100


def test_format_components_exact():
    assert format_components(score_record(_record("=NOW()"))) == "VOLATILE_FUNCTION: +15"
    ladder = "=IF(B2<1000,0.05,IF(B2<5000,0.08,IF(B2<10000,0.12,0.15)))"
    assert format_components(score_record(_record(ladder, "C2"))) == "NESTED_IF_DEPTH_3: +15"
    assert format_components(score_record(_record("=E2*F2", "G2"))) == ""


def test_contract_adapter_round_trips():
    result = score_record(_record("=NOW()"))
    risk = to_contract_risk(result)
    assert isinstance(risk, Risk)
    assert risk.score == 15
    assert risk.flags == ["VOLATILE_FUNCTION"]
    assert Risk.model_validate_json(risk.model_dump_json()) == risk


def test_every_pattern_has_explicit_risk_decision():
    rules = load_rules()
    flags = pattern_flags()
    for spec in load_patterns():
        assert spec["id"] in flags, f"no risk decision for pattern {spec['id']}"
    for flag in sorted({f for f in flags.values() if f is not None}):
        assert flag in rules, f"no points for flag {flag}"


def test_determinism_20_runs():
    formulas = ["=NOW()", "=IFERROR(B2/C2,0)", "=MEDIAN(A1:A10)", "=E2*F2"]
    first = [score_record(_record(f)) for f in formulas]
    for _ in range(20):
        assert [score_record(_record(f)) for f in formulas] == first
    dumped = [to_contract_risk(r).model_dump_json() for r in first]
    assert [to_contract_risk(r).model_dump_json() for r in first] == dumped
