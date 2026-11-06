"""FX and treasury vocabulary: headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Exchange_Rate", "exchange rate"),
    ("FX_Rate", "fx rate"),
    ("Spot_Rate", "spot rate"),
    ("Forward_Rate", "forward rate"),
    ("Closing_Rate", "closing rate"),
    ("Average_Rate", "average rate"),
    ("Avg_Rate", "average rate"),
    ("Base_Currency", "base currency"),
    ("Local_Currency", "local currency"),
    ("Reporting_Currency", "reporting currency"),
    ("Functional_Currency", "functional currency"),
    ("Currency_Code", "currency code"),
    ("USD_Amount", "usd amount"),
    ("EUR_Rate", "eur rate"),
    ("INR_Value", "inr value"),
    ("GBP_Balance", "gbp balance"),
    ("Translation_Adjustment", "translation adjustment"),
    ("Unrealized_Gain", "unrealized gain"),
    ("Realized_Loss", "realized loss"),
    ("Hedge_Ratio", "hedge ratio"),
    ("Hedging_Cost", "hedging cost"),
    ("Forward_Contract", "forward contract"),
    ("Swap_Rate", "swap rate"),
    ("Notional_Amount", "notional amount"),
    ("Maturity_Date", "maturity date"),
    ("Settlement_Date", "settlement date"),
    ("Value_Date", "value date"),
    ("Counterparty", "counterparty"),
    ("Bid_Price", "bid price"),
    ("Ask_Price", "ask price"),
    ("Mid_Rate", "mid rate"),
    ("Pips", "pip"),
    ("Spread", "spread"),
    ("Exposure", "exposure"),
    ("Currencies", "currency"),
    ("Rates", "rate"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_existing_terms_unchanged() -> None:
    assert load_lexicon().resolve("FX").phrase == "fx"
    assert load_lexicon().resolve("Rate").phrase == "rate"
    assert load_lexicon().resolve("Date").phrase == "date"
    assert load_lexicon().resolve("Value").phrase == "value"
    assert load_lexicon().resolve("Gain").phrase == "gain"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Hedge_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
