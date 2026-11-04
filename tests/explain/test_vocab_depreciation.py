"""Depreciation and fixed-asset vocabulary: headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Accumulated_Depreciation", "accumulated depreciation"),
    ("Acc_Depreciation", "accumulated depreciation"),
    ("Depreciation_Charge", "depreciation charge"),
    ("Depr_Expense", "depreciation expense"),
    ("Opening_WDV", "opening wdv"),
    ("Written_Down_Value", "written down value"),
    ("NBV", "nbv"),
    ("Net_Book_Value", "net book value"),
    ("Book_Value", "book value"),
    ("Carrying_Amount", "carrying amount"),
    ("Residual_Value", "residual value"),
    ("Salvage_Value", "salvage value"),
    ("Scrap_Value", "scrap value"),
    ("Useful_Life", "useful life"),
    ("Asset_Life", "asset life"),
    ("Asset_Class", "asset class"),
    ("Asset_Register", "asset register"),
    ("Straight_Line", "straight line"),
    ("SLM", "slm"),
    ("Declining_Balance", "declining balance"),
    ("Units_of_Production", "unit of production"),
    ("Gross_Block", "gross block"),
    ("Net_Block", "net block"),
    ("Additions", "addition"),
    ("Disposals", "disposal"),
    ("Disposal_Proceeds", "disposal proceeds"),
    ("Gain_on_Disposal", "gain on disposal"),
    ("Impairment_Loss", "impairment loss"),
    ("Revaluation_Reserve", "revaluation reserve"),
    ("Capex", "capex"),
    ("CWIP", "cwip"),
    ("Capital_Work_in_Progress", "capital work in progress"),
    ("Acquisition_Date", "acquisition date"),
    ("Purchase_Date", "purchase date"),
    ("Accum_Dep", "accumulated depreciation"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_existing_terms_unchanged() -> None:
    assert load_lexicon().resolve("Depreciation").phrase == "depreciation"
    assert load_lexicon().resolve("Dep").phrase == "depreciation"
    assert load_lexicon().resolve("Depr").phrase == "depreciation"
    assert load_lexicon().resolve("Unit").phrase == "unit"
    assert load_lexicon().resolve("Units").phrase == "unit"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Impairment_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
