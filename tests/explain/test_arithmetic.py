"""General fallbacks: arithmetic read aloud, links, and risk of nested idioms."""

import pytest

from archon.explain.from_formula import explain_tree
from archon.explain.matcher import match_formula
from archon.explain.risk import score_record


def _run(formula: str, cell: str = "D2"):
    record = match_formula("n", cell, explain_tree(formula))
    return record, score_record(record)


def test_specific_idioms_still_win_over_the_fallback():
    record, _ = _run("=A2*B2")
    assert record.evidence.pattern_id == "product"


def test_arithmetic_with_a_typed_number_is_read_exactly_and_flagged():
    record, risk = _run("=B2*0.05+B4")
    assert record.plain_english == (
        "Calculates (B2 multiplied by 0.05) plus B4; uses a number typed into the formula (0.05)."
    )
    assert risk.flags == ("EMBEDDED_CONSTANT",)


@pytest.mark.parametrize("formula", ["=1-C2", "=C2/100", "=C2*1+B2"])
def test_structural_numbers_are_not_flagged(formula):
    record, risk = _run(formula)
    assert record.evidence.pattern_id == "arithmetic"
    assert risk.score == 0


def test_nested_lookup_is_explained_and_its_risk_counts():
    record, risk = _run("=C2*VLOOKUP(C2,Inputs!$A$2:$B$4,2)")
    assert record.plain_english == (
        "Calculates C2 multiplied by the column 2 value for C2 in Inputs!A2:B4 "
        "(approximate match by default)."
    )
    assert risk.flags == ("APPROX_LOOKUP_DEFAULT",)


def test_nested_sum():
    record, _ = _run("=SUM(A1:A9)/B2")
    assert record.plain_english == "Calculates the total of A1:A9 divided by B2."


def test_link_to_another_cell():
    record, risk = _run("=Inputs!$D$2")
    assert record.plain_english == "Takes the value of Inputs!D2."
    assert risk.score == 0


def test_sheet_qualified_lookup_table_is_recognised():
    record, _ = _run("=VLOOKUP(C2,Inputs!A2:B4,2,0)")
    assert record.evidence.pattern_id == "vlookup_exact"


@pytest.mark.parametrize("formula", ["=C2*MEDIAN(A1:A9)", "=C2*(A1>0)", "=MAX(A1,B1)"])
def test_unknown_parts_stay_unverified(formula):
    record, _ = _run(formula)
    assert record.status == "unverified"
