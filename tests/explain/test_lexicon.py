"""Lexicon: split a column header into terms and resolve them (Days 5-6)."""

from archon.explain.lexicon import Lexicon, split_header

ENTRIES = {
    "gross": ["grs"],
    "revenue": ["rev", "sales"],
    "tax": [],
}


def _lex() -> Lexicon:
    return Lexicon.from_entries(ENTRIES)


def test_split_underscore() -> None:
    assert split_header("Gross_Revenue") == ("gross", "revenue")


def test_split_camel_case() -> None:
    assert split_header("grossRevenue") == ("gross", "revenue")


def test_split_pascal_case() -> None:
    assert split_header("GrossRevenue") == ("gross", "revenue")


def test_split_spaces_and_hyphens() -> None:
    assert split_header("gross revenue") == ("gross", "revenue")
    assert split_header("Gross-Revenue") == ("gross", "revenue")


def test_split_empty_and_symbols() -> None:
    assert split_header("") == ()
    assert split_header("  __ ") == ()


def test_resolve_all_terms() -> None:
    res = _lex().resolve("Gross_Revenue")
    assert res.resolved is True
    assert res.terms == ("gross", "revenue")
    assert res.unresolved == ()
    assert res.phrase == "gross revenue"


def test_resolve_alias_maps_to_canonical() -> None:
    res = _lex().resolve("Rev")
    assert res.resolved is True
    assert res.terms == ("revenue",)
    assert res.phrase == "revenue"


def test_resolve_partial_is_not_resolved() -> None:
    res = _lex().resolve("Gross_Foo")
    assert res.resolved is False
    assert res.terms == ("gross",)
    assert res.unresolved == ("foo",)


def test_resolve_unknown_and_empty() -> None:
    assert _lex().resolve("Zzz").resolved is False
    empty = _lex().resolve("")
    assert empty.resolved is False
    assert empty.terms == ()
    assert empty.phrase == ""


def test_alias_collision_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="rev"):
        Lexicon.from_entries({"revenue": ["rev"], "reverse": ["rev"]})


def test_resolution_is_deterministic() -> None:
    first = _lex().resolve("Gross_Revenue")
    for _ in range(20):
        assert _lex().resolve("Gross_Revenue") == first
