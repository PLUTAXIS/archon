"""Lookups: VLOOKUP (exact / approximate / default) and INDEX-MATCH exact."""

from archon.contracts.explain import ExplanationRecord
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula

LEAD = "Looks up A2 in the first column of F1:H20 and returns column 3"


def _run(formula: str, cell: str = "D2") -> ExplanationRecord:
    return match_formula("n1", cell, parse_mock_formula(formula))


def _assert_matched(
    result: ExplanationRecord,
    pattern_id: str,
    sentence: str,
    captured: dict[str, str],
) -> None:
    assert result.status == "matched"
    assert result.idiom == "lookup"
    assert result.plain_english == sentence
    assert result.confidence == 1.0
    assert result.evidence is not None
    assert result.evidence.pattern_id == pattern_id
    assert result.evidence.captured_vars == captured


def test_vlookup_exact() -> None:
    _assert_matched(
        _run("=VLOOKUP(A2,F1:H20,3,0)"),
        "vlookup_exact",
        f"{LEAD} (exact match).",
        {"key": "A2", "table": "F1:H20", "column": "3", "match": "exact"},
    )


def test_vlookup_approx() -> None:
    _assert_matched(
        _run("=VLOOKUP(A2,F1:H20,3,1)"),
        "vlookup_approx",
        f"{LEAD} (approximate match).",
        {"key": "A2", "table": "F1:H20", "column": "3", "match": "approximate"},
    )


def test_vlookup_default_is_flagged_as_approximate() -> None:
    _assert_matched(
        _run("=VLOOKUP(A2,F1:H20,3)"),
        "vlookup_default",
        f"{LEAD} (approximate match, the default).",
        {"key": "A2", "table": "F1:H20", "column": "3"},
    )


def test_index_match_exact() -> None:
    _assert_matched(
        _run("=INDEX(C1:C20,MATCH(A2,B1:B20,0))"),
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


def test_vlookup_other_match_mode_is_unverified() -> None:
    assert _run("=VLOOKUP(A2,F1:H20,3,2)").status == "unverified"


def test_vlookup_expression_key_is_unverified() -> None:
    assert _run("=VLOOKUP(A2*2,F1:H20,3,0)").status == "unverified"


def test_vlookup_non_integer_column_is_unverified() -> None:
    assert _run("=VLOOKUP(A2,F1:H20,1.5,0)").status == "unverified"


def test_vlookup_wrong_arg_count_is_unverified() -> None:
    assert _run("=VLOOKUP(A2,F1:H20)").status == "unverified"
    assert _run("=VLOOKUP(A2,F1:H20,3,0,1)").status == "unverified"


def test_index_match_approximate_is_unverified() -> None:
    assert _run("=INDEX(C1:C20,MATCH(A2,B1:B20,1))").status == "unverified"


def test_index_without_match_is_unverified() -> None:
    assert _run("=INDEX(C1:C20,3)").status == "unverified"
