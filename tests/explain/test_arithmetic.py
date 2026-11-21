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


@pytest.mark.parametrize("formula", ["=C2*MIRR(A1:A9)", "=C2*(A1>0)", "=IRR(A1,B1)"])
def test_unknown_parts_stay_unverified(formula):
    record, _ = _run(formula)
    assert record.status == "unverified"


@pytest.mark.parametrize(
    ("formula", "text"),
    [
        ("=AVERAGE(C2:C9)", "The average of C2:C9."),
        ("=MAX(A1,0)", "The largest of A1 and 0."),
        ("=SUM(A1,B1,C1)", "The total of A1, B1 and C1."),
        ("=LEFT(A1,3)", "The first 3 characters of A1."),
        ("=MIN(A1:A9)/MAX(A1:A9)", "Calculates the smallest of A1:A9 divided by the largest of A1:A9."),
    ],
)
def test_listed_functions_are_read_aloud_without_risk(formula, text):
    record, risk = _run(formula)
    assert record.plain_english == text
    assert risk.score == 0


def test_if_reads_condition_and_flags_typed_in_thresholds():
    record, risk = _run("=IF(C2>500,C2*0.2,0)")
    assert record.plain_english == (
        "If C2 is greater than 500, C2 multiplied by 0.2; otherwise 0; "
        "uses a number typed into the formula (500, 0.2)."
    )
    assert risk.flags == ("EMBEDDED_CONSTANT",)


def test_conditions_and_text():
    record, _ = _run('=IF(AND(A1>0,B1<1),"ok","check")')
    assert record.plain_english == (
        "If all of (A1 is greater than 0 and B1 is less than 1) hold, “ok”; otherwise “check”."
    )
    record, _ = _run('="Total: "&A1')
    assert record.plain_english == "Calculates “Total: ” followed by A1."


@pytest.mark.parametrize("formula", ["=ROUND(A1,1.5)", "=LEFT(A1)", "=A1>B1", "=SUM()"])
def test_misleading_or_incomplete_calls_stay_unverified(formula):
    record, _ = _run(formula)
    assert record.status == "unverified"
