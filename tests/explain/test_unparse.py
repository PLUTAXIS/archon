"""to_formula_text: canonical, deterministic text for a sub-expression."""

from archon.explain.formula_ast import parse_mock_formula, to_formula_text


def _text(formula: str) -> str:
    return to_formula_text(parse_mock_formula(formula))


def test_binary() -> None:
    assert _text("=B2/C2") == "B2/C2"


def test_nested_binary_is_parenthesised() -> None:
    assert _text("=(B2+C2)*D2") == "(B2+C2)*D2"
    assert _text("=B2*C2+D2") == "(B2*C2)+D2"


def test_call_and_range() -> None:
    assert _text("=SUM(A1:A10)") == "SUM(A1:A10)"
    assert _text("=IF(B2<1000,0.05,0.15)") == "IF(B2<1000,0.05,0.15)"


def test_zero_arg_call() -> None:
    assert _text("=NOW()") == "NOW()"
