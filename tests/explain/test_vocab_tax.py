"""Tax vocabulary: real-world headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("VAT_Payable", "vat payable"),
    ("GST_Rate", "gst rate"),
    ("Withholding_Tax", "withholding tax"),
    ("TDS_Amount", "tds amount"),
    ("Taxable_Income", "taxable income"),
    ("Income_Tax_Expense", "income tax expense"),
    ("Deferred_Tax_Liability", "deferred tax liability"),
    ("Effective_Tax_Rate", "effective tax rate"),
    ("Tax_Refund", "tax refund"),
    ("Tax_Credit", "tax credit"),
    ("Input_Tax_Credit", "input tax credit"),
    ("Output_Tax", "output tax"),
    ("Advance_Tax", "advance tax"),
    ("Tax_Deductions", "tax deduction"),
    ("Exemptions", "exemption"),
    ("Surcharge", "surcharge"),
    ("Cess", "cess"),
    ("Customs_Duty", "customs duty"),
    ("Excise_Duty", "excise duty"),
    ("Stamp_Duty", "stamp duty"),
    ("Tax_Penalty", "tax penalty"),
    ("Statutory_Rate", "statutory rate"),
    ("Marginal_Rate", "marginal rate"),
    ("Corporate_Tax", "corporate tax"),
    ("Tax_Assessment", "tax assessment"),
    ("Pre_Tax_Profit", "pre tax profit"),
    ("Post_Tax_Income", "post tax income"),
    ("Duties", "duty"),
    ("Penalties", "penalty"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_existing_terms_unchanged() -> None:
    assert load_lexicon().resolve("Tax").phrase == "tax"
    assert load_lexicon().resolve("Taxes").phrase == "tax"
    assert load_lexicon().resolve("Rate").phrase == "rate"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Cess_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
