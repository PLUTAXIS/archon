"""Tests for the deterministic formula pattern matcher (Day 2)."""

from archon.contracts.explain import ExplanationRecord
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula

TIERED = "=IF(B2<1000,0.05,IF(B2<5000,0.08,IF(B2<10000,0.12,0.15)))"
BRACKETS = "1000:0.05|5000:0.08|10000:0.12|default:0.15"


def _assert_unverified(result: ExplanationRecord, node_id: str) -> None:
    """An unverified record carries no explanation and zero confidence."""
    assert result.node_id == node_id
    assert result.status == "unverified"
    assert result.idiom is None
    assert result.plain_english is None
    assert result.business_concept is None
    assert result.evidence is None
    assert result.confidence == 0.0


def test_positive_tiered_rate_table() -> None:
    """Matches a 3+ deep nested IF pivoting on a single variable."""
    tree = parse_mock_formula(TIERED)
    result = match_formula(node_id="n1", cell_address="C2", tree=tree)

    assert result.node_id == "n1"
    assert result.status == "matched"
    assert result.idiom == "tiered_rate_table"
    assert result.plain_english == (
        "Tiered rate table pivoting on B2 with 4 brackets."
    )
    assert result.confidence == 1.0
    assert result.evidence is not None
    assert result.evidence.header_resolved is False
    assert result.evidence.captured_vars["pivot"] == "B2"
    assert result.evidence.captured_vars["brackets"] == BRACKETS


def test_positive_running_balance() -> None:
    """Matches a running balance referencing the prior row, same column."""
    tree = parse_mock_formula("=D1+B2-C2")
    result = match_formula(node_id="n2", cell_address="D2", tree=tree)

    assert result.node_id == "n2"
    assert result.status == "matched"
    assert result.idiom == "running_balance"
    assert result.plain_english == (
        "Running balance from D1, adding B2, subtracting C2."
    )
    assert result.confidence == 1.0
    assert result.evidence is not None
    assert result.evidence.header_resolved is False
    assert result.evidence.captured_vars["prior_row"] == "D1"
    assert result.evidence.captured_vars["added"] == "B2"
    assert result.evidence.captured_vars["subtracted"] == "C2"


def test_negative_plain_sum() -> None:
    """An unsupported MEDIAN matches neither the tiered nor running balance idiom."""
    result = match_formula("n3", "B1", parse_mock_formula("=MEDIAN(A1:A10)"))
    _assert_unverified(result, "n3")


def test_negative_2_deep_if() -> None:
    """A 2-deep IF ladder must NOT match as tiered_rate_table (needs 3+)."""
    tree = parse_mock_formula("=IF(B2<1000,0.05,IF(B2<5000,0.08,0.15))")
    _assert_unverified(match_formula("n4", "C2", tree), "n4")


def test_negative_2_variable_if() -> None:
    """A nested IF pivoting on TWO different variables must NOT match."""
    formula = "=IF(B2<1000,0.05,IF(C2<5000,0.08,IF(B2<10000,0.12,0.15)))"
    _assert_unverified(match_formula("n5", "D2", parse_mock_formula(formula)), "n5")


def test_negative_unknown_function() -> None:
    """An unknown function returns unverified without crashing."""
    tree = parse_mock_formula("=UNKNOWN_FUNC(A1)")
    _assert_unverified(match_formula("n6", "B1", tree), "n6")


def test_negative_balance_prior_ref_wrong_column() -> None:
    """C1 is not in the same column as D2, so this is not a running balance."""
    tree = parse_mock_formula("=C1+B2-C2")
    _assert_unverified(match_formula("n8", "D2", tree), "n8")


def test_negative_balance_not_row_above() -> None:
    """D1 referenced from D5 is not the row above."""
    tree = parse_mock_formula("=D1+B5-C5")
    _assert_unverified(match_formula("n9", "D5", tree), "n9")


def test_negative_self_reference_same_cell() -> None:
    """A reference to its own cell is circular, not a running balance."""
    tree = parse_mock_formula("=D2+B2")
    _assert_unverified(match_formula("n10", "D2", tree), "n10")


def test_determinism_byte_identical_output() -> None:
    """Identical inputs must produce byte-identical JSON."""
    tree = parse_mock_formula(TIERED)
    res1 = match_formula("n7", "C2", tree).model_dump_json()
    res2 = match_formula("n7", "C2", tree).model_dump_json()
    assert res1 == res2


def test_determinism_stable_across_many_runs() -> None:
    """Twenty runs on the same input all serialize identically."""
    tree = parse_mock_formula("=D1+B2-C2")
    first = match_formula("n12", "D2", tree).model_dump_json()
    for _ in range(20):
        assert match_formula("n12", "D2", tree).model_dump_json() == first
