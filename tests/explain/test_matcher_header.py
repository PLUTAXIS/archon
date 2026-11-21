"""Header resolution is recorded in the evidence of a matched record."""

from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula

PRODUCT = parse_mock_formula("=E2*F2")


def test_resolved_header_is_recorded() -> None:
    result = match_formula("h1", "G2", PRODUCT, header="Gross_Revenue")
    assert result.evidence is not None
    assert result.evidence.header_resolved is True
    assert result.evidence.header_terms == ["gross", "revenue"]


def test_no_header_keeps_unresolved() -> None:
    result = match_formula("h2", "G2", PRODUCT)
    assert result.evidence is not None
    assert result.evidence.header_resolved is False
    assert result.evidence.header_terms == []


def test_unknown_header_is_unresolved() -> None:
    result = match_formula("h3", "G2", PRODUCT, header="Zzz")
    assert result.evidence is not None
    assert result.evidence.header_resolved is False
    assert result.evidence.header_terms == []


def test_header_never_rescues_an_unmatched_formula() -> None:
    tree = parse_mock_formula("=MIRR(A1:A10)")
    result = match_formula("h4", "B1", tree, header="Gross_Revenue")
    assert result.status == "unverified"
    assert result.evidence is None
    assert result.confidence == 0.0
