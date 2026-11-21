import pytest

from archon.explain.formula_ast import (
    BinOp,
    Call,
    Num,
    Range,
    Ref,
    Str,
    parse_mock_formula,
)
from archon.explain.from_formula import explain_tree
from archon.explain.matcher import match_formula


def test_simple_formulas_keep_the_explain_parser_result():
    for f in ("=A2*B2", "=IF(C2>100,0.3,0)", "=SUM(A1:A10)"):
        assert explain_tree(f) == parse_mock_formula(f)


def test_sheet_qualified_refs_and_ranges():
    assert explain_tree("=Inputs!$B$2*Inputs!C2") == BinOp(
        "*", Ref("Inputs!B2"), Ref("Inputs!C2")
    )
    assert explain_tree("=SUM(Data!A1:A10)") == Call("SUM", (Range("Data!A1", "A10"),))


def test_unary_minus_and_percent_become_numbers():
    assert explain_tree("=A1*-2") == BinOp("*", Ref("A1"), Num("-2"))
    assert explain_tree("=A1*5%") == BinOp("*", Ref("A1"), Num("0.05"))


@pytest.mark.parametrize(
    "formula",
    ["=A1^2", "=TaxRate*A1", "=IF(A1,TRUE,FALSE)", "=-A1", "=SUM(A:A)", "=(("],
)
def test_unrepresentable_formulas_raise_instead_of_guessing(formula):
    with pytest.raises(ValueError):
        explain_tree(formula)


def test_text_and_joining_are_represented():
    assert explain_tree('="x"&A1') == BinOp("&", Str("x"), Ref("A1"))


def test_sheet_qualified_formula_now_gets_explained():
    record = match_formula("n", "C2", explain_tree("=Inputs!B2*Inputs!C2"))
    assert record.status == "matched"
