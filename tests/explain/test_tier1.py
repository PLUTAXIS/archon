"""Tier 1 idioms: product, sum, difference, ratio, rounding (Days 3-4)."""

from archon.contracts.explain import ExplanationRecord
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula


def _run(node_id: str, cell: str, formula: str) -> ExplanationRecord:
    return match_formula(node_id, cell, parse_mock_formula(formula))


def _assert_matched(
    result: ExplanationRecord,
    node_id: str,
    idiom: str,
    sentence: str,
    captured: dict[str, str],
) -> None:
    assert result.node_id == node_id
    assert result.status == "matched"
    assert result.idiom == idiom
    assert result.plain_english == sentence
    assert result.confidence == 1.0
    assert result.evidence is not None
    assert result.evidence.pattern_id == idiom
    assert result.evidence.header_resolved is False
    assert result.evidence.captured_vars == captured


def _assert_unverified(result: ExplanationRecord, node_id: str) -> None:
    assert result.node_id == node_id
    assert result.status == "unverified"
    assert result.idiom is None
    assert result.plain_english is None
    assert result.business_concept is None
    assert result.evidence is None
    assert result.confidence == 0.0


def test_product() -> None:
    _assert_matched(
        _run("t1", "G2", "=E2*F2"), "t1", "product",
        "Product of E2 and F2.", {"left": "E2", "right": "F2"},
    )


def test_sum_range() -> None:
    _assert_matched(
        _run("t2", "B11", "=SUM(A1:A10)"), "t2", "sum",
        "Sum of A1:A10.", {"range": "A1:A10"},
    )


def test_difference() -> None:
    _assert_matched(
        _run("t3", "D2", "=B2-C2"), "t3", "difference",
        "Difference of B2 minus C2.", {"minuend": "B2", "subtrahend": "C2"},
    )


def test_ratio() -> None:
    _assert_matched(
        _run("t4", "D2", "=B2/C2"), "t4", "ratio",
        "Ratio of B2 to C2.", {"numerator": "B2", "denominator": "C2"},
    )


def test_rounding() -> None:
    _assert_matched(
        _run("t5", "C2", "=ROUND(B2,2)"), "t5", "rounding",
        "B2 rounded to 2 decimal places.", {"value": "B2", "digits": "2"},
    )


def test_balance_still_wins_over_difference() -> None:
    """D1-C2 in D2 subtracts the row above: a running balance, not a difference."""
    result = _run("t6", "D2", "=D1-C2")
    assert result.status == "matched"
    assert result.idiom == "running_balance"


def test_negative_product_of_three() -> None:
    _assert_unverified(_run("n1", "H2", "=E2*F2*G2"), "n1")


def test_negative_product_with_constant() -> None:
    _assert_unverified(_run("n2", "G2", "=E2*1.2"), "n2")


def test_negative_ratio_by_constant() -> None:
    _assert_unverified(_run("n3", "D2", "=B2/100"), "n3")


def test_negative_sum_two_arguments() -> None:
    _assert_unverified(_run("n4", "C1", "=SUM(A1,B1)"), "n4")


def test_negative_round_one_argument() -> None:
    _assert_unverified(_run("n5", "C2", "=ROUND(B2)"), "n5")


def test_negative_round_of_expression() -> None:
    _assert_unverified(_run("n6", "D2", "=ROUND(B2*C2,2)"), "n6")


def test_determinism_all_tier1() -> None:
    cases = [
        ("=E2*F2", "G2"), ("=SUM(A1:A10)", "B11"), ("=B2-C2", "D2"),
        ("=B2/C2", "D2"), ("=ROUND(B2,2)", "C2"),
    ]
    first = [_run("x", c, f).model_dump_json() for f, c in cases]
    for _ in range(20):
        assert [_run("x", c, f).model_dump_json() for f, c in cases] == first
