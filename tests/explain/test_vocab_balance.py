"""Balance-sheet vocabulary: real-world headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Accounts_Receivable", "account receivable"),
    ("AccountsPayable", "account payable"),
    ("AR_Balance", "receivable balance"),
    ("AP_Balance", "payable balance"),
    ("Total_Assets", "total asset"),
    ("Total_Liabilities", "total liability"),
    ("Current_Assets", "current asset"),
    ("NonCurrent_Liabilities", "non current liability"),
    ("Fixed_Assets", "fixed asset"),
    ("Intangible_Assets", "intangible asset"),
    ("Long_Term_Debt", "long term debt"),
    ("Short_Term_Borrowings", "short term borrowing"),
    ("Property_Plant_Equipment", "property plant equipment"),
    ("PPE_Net", "ppe net"),
    ("Accrued_Expenses", "accrued expense"),
    ("Deferred_Revenue", "deferred revenue"),
    ("Prepaid_Expenses", "prepaid expense"),
    ("Goodwill", "goodwill"),
    ("Working_Capital", "working capital"),
    ("Share_Capital", "share capital"),
    ("Treasury_Shares", "treasury share"),
    ("Lease_Liabilities", "lease liability"),
    ("Cash_Equivalents", "cash equivalent"),
    ("Reserves", "reserve"),
    ("Loans", "loan"),
    ("Investments", "investment"),
    ("Provisions", "provision"),
    ("Net_Debt", "net debt"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_plural_aliases_keep_existing_terms() -> None:
    assert load_lexicon().resolve("Asset").phrase == "asset"
    assert load_lexicon().resolve("Liability").phrase == "liability"
    assert load_lexicon().resolve("Expense").phrase == "expense"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Goodwill_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
