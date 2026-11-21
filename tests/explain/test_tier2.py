"""Tier 2 (part 1): error suppression and volatile functions."""

from archon.contracts.explain import ExplanationRecord
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula


def _run(node_id: str, cell: str, formula: str) -> ExplanationRecord:
    return match_formula(node_id, cell, parse_mock_formula(formula))


def _assert_matched(
    result: ExplanationRecord,
    node_id: str,
    idiom: str,
    pattern_id: str,
    sentence: str,
    captured: dict[str, str],
) -> None:
    assert result.node_id == node_id
    assert result.status == "matched"
    assert result.idiom == idiom
    assert result.plain_english == sentence
    assert result.confidence == 1.0
    assert result.evidence is not None
    assert result.evidence.pattern_id == pattern_id
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


def test_iferror_with_number_fallback() -> None:
    _assert_matched(
        _run("e1", "D2", "=IFERROR(B2/C2,0)"), "e1", "error_suppression",
        "error_suppression",
        "Evaluates B2 divided by C2 and replaces any error with 0.",
        {"expression": "B2/C2", "fallback": "0"},
    )


def test_iferror_with_reference_fallback() -> None:
    _assert_matched(
        _run("e2", "D2", "=IFERROR(SUM(A1:A10),E2)"), "e2", "error_suppression",
        "error_suppression",
        "Evaluates the total of A1:A10 and replaces any error with E2.",
        {"expression": "SUM(A1:A10)", "fallback": "E2", "embedded": "sum"},
    )


def test_negative_iferror_one_argument() -> None:
    _assert_unverified(_run("n1", "D2", "=IFERROR(B2/C2)"), "n1")


def test_negative_iferror_expression_fallback() -> None:
    _assert_unverified(_run("n2", "D2", "=IFERROR(B2/C2,D2*2)"), "n2")


def test_now() -> None:
    _assert_matched(
        _run("v1", "A1", "=NOW()"), "v1", "volatile_function", "volatile_now",
        "Current date and time; recalculates on every change.", {},
    )


def test_today() -> None:
    _assert_matched(
        _run("v2", "A1", "=TODAY()"), "v2", "volatile_function", "volatile_today",
        "Today's date; recalculates on every change.", {},
    )


def test_rand() -> None:
    _assert_matched(
        _run("v3", "A1", "=RAND()"), "v3", "volatile_function", "volatile_rand",
        "Random number between 0 and 1; recalculates on every change.", {},
    )


def test_negative_now_with_argument() -> None:
    _assert_unverified(_run("n3", "A1", "=NOW(1)"), "n3")


def test_determinism_tier2() -> None:
    cases = [("=IFERROR(B2/C2,0)", "D2"), ("=NOW()", "A1"), ("=RAND()", "A1")]
    first = [_run("x", c, f).model_dump_json() for f, c in cases]
    for _ in range(20):
        assert [_run("x", c, f).model_dump_json() for f, c in cases] == first
