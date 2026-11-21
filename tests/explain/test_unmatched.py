"""Unmatched-shapes report: canonical shape keys, ranked by frequency."""

from archon.explain.formula_ast import Node, parse_mock_formula
from archon.explain.unmatched import ShapeCount, rank_unmatched, shape_key


def _tree(formula: str) -> Node:
    return parse_mock_formula(formula)


def _items(formulas: list[str]) -> list[tuple[str, str, Node]]:
    return [(f"n{i}", "G2", _tree(f)) for i, f in enumerate(formulas)]


def test_shape_key_ignores_which_cells() -> None:
    assert shape_key(_tree("=MIRR(A1:A10)")) == "MIRR(<range>)"
    assert shape_key(_tree("=MIRR(B5:B99)")) == "MIRR(<range>)"


def test_shape_key_distinguishes_structure() -> None:
    assert shape_key(_tree("=IRR(B2,C2)")) == "IRR(<ref>,<ref>)"
    assert shape_key(_tree("=IRR(B2,1.5)")) == "IRR(<ref>,<num>)"
    assert shape_key(_tree("=B2*1.2")) == "(<ref>*<num>)"


def test_shape_key_zero_arg_call() -> None:
    assert shape_key(_tree("=FOO()")) == "FOO()"


def test_ranked_by_count_descending() -> None:
    result = rank_unmatched(
        _items(
            [
                "=MIRR(A1:A10)",
                "=FV(B2:B9)",
                "=MIRR(B1:B50)",
                "=IRR(B2,C2)",
                "=MIRR(C1:C5)",
                "=FV(D2:D9)",
            ]
        )
    )
    assert result == (
        ShapeCount("MIRR(<range>)", 3),
        ShapeCount("FV(<range>)", 2),
        ShapeCount("IRR(<ref>,<ref>)", 1),
    )


def test_ties_broken_alphabetically() -> None:
    result = rank_unmatched(_items(["=NPV(B2,C2)", "=IRR(B2,C2)"]))
    assert [s.shape for s in result] == ["IRR(<ref>,<ref>)", "NPV(<ref>,<ref>)"]


def test_matched_formulas_are_excluded() -> None:
    result = rank_unmatched(_items(["=E2*F2", "=NOW()", "=MIRR(A1:A10)"]))
    assert result == (ShapeCount("MIRR(<range>)", 1),)


def test_empty_input() -> None:
    assert rank_unmatched([]) == ()


def test_input_order_does_not_matter() -> None:
    items = _items(["=MIRR(A1:A10)", "=B2*1.2", "=IRR(B2,C2)", "=MIRR(B1:B2)"])
    assert rank_unmatched(items) == rank_unmatched(list(reversed(items)))


def test_determinism() -> None:
    items = _items(["=MIRR(A1:A10)", "=B2*1.2", "=MIRR(B1:B2)"])
    first = rank_unmatched(items)
    for _ in range(20):
        assert rank_unmatched(items) == first
