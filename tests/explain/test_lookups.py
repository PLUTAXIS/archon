"""Tier 2 (part 2): lookups (VLOOKUP, INDEX-MATCH)."""

from archon.contracts.explain import ExplanationRecord
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula


def _run(node_id: str, cell: str, formula: str) -> ExplanationRecord:
    return match_formula(node_id, cell, parse_mock_formula(formula))


def _assert_matched(
    result: ExplanationRecord,
    node_id: str,
    pattern_id: str,
    sentence: str,
    captured: dict[str, str],
) -> None:
    assert result.node_id == node_id
    assert result.status == "matched"
    assert result.idiom == "lookup"
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


def test_vlookup_exact() -> None:
    _assert_matched(
        _run("l1", "D2", "=VLOOKUP(A2,F1:H20,3,0)"), "l1", "vlookup_exact",
        "Looks up A2 in the first column of F1:H20 and returns column 3 "
        "(exact match).",
        {"key": "A2", "table": "F1:H20", "column": "3", "match": "exact"},
    )


def test_vlookup_approximate() -> None:
    _assert_matched(
        _run("l2", "D2", "=VLOOKUP(A2,F1:H20,3,1)"), "l2", "vlookup_approx",
        "Looks up A2 in the first column of F1:H20 and returns column 3 "
        "(approximate match).",
        {"key": "A2", "table": "F1:H20", "column": "3", "match": "approximate"},
    )


def test_vlookup_default_is_approximate() -> None:
    """Omitting the 4th argument means approximate match; the sentence says so."""
    _assert_matched(
        _run("l3", "D2", "=VLOOKUP(A2,F1:H20,3)"), "l3", "vlookup_default",
        "Looks up A2 in the first column of F1:H20 and returns column 3 "
        "(approximate match, the default).",
        {"key": "A2", "table": "F1:H20", "column": "3"},
    )


def test_index_match_exact() -> None:
    _assert_matched(
        _run("l4", "D2", "=INDEX(C1:C20,MATCH(A2,B1:B20,0))"), "l4",
        "index_match_exact",
        "Looks up A2 in B1:B20 and returns the matching value from C1:C20 "
        "(exact match).",
        {
            "key": "A2",
            "lookup_range": "B1:B20",
            "result_range": "C1:C20",
            "match": "exact",
        },
    )


def test_negative_vlookup_fractional_column() -> None:
    _assert_unverified(_run("n1", "D2", "=VLOOKUP(A2,F1:H20,2.5,0)"), "n1")


def test_negative_vlookup_expression_key() -> None:
    _assert_unverified(_run("n2", "D2", "=VLOOKUP(A2+1,F1:H20,3,0)"), "n2")


def test_negative_vlookup_unknown_match_mode() -> None:
    _assert_unverified(_run("n3", "D2", "=VLOOKUP(A2,F1:H20,3,2)"), "n3")


def test_negative_index_match_approximate_mode() -> None:
    _assert_unverified(_run("n4", "D2", "=INDEX(C1:C20,MATCH(A2,B1:B20,1))"), "n4")


def test_negative_index_without_match() -> None:
    _assert_unverified(_run("n5", "D2", "=INDEX(C1:C20,5)"), "n5")


def test_determinism_lookups() -> None:
    cases = [
        ("=VLOOKUP(A2,F1:H20,3,0)", "D2"),
        ("=VLOOKUP(A2,F1:H20,3)", "D2"),
        ("=INDEX(C1:C20,MATCH(A2,B1:B20,0))", "D2"),
    ]
    first = [_run("x", c, f).model_dump_json() for f, c in cases]
    for _ in range(20):
        assert [_run("x", c, f).model_dump_json() for f, c in cases] == first
