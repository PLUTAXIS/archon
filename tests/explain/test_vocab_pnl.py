"""P&L vocabulary: real-world headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Gross_Profit", "gross profit"),
    ("OperatingExpenses", "operating expense"),
    ("EBIT_Margin", "ebit margin"),
    ("Net_Sales", "net revenue"),
    ("Profit_Before_Tax", "profit before tax"),
    ("Budget_vs_Actual", "budget vs actual"),
    ("Cost_of_Goods_Sold", "cost of goods sold"),
    ("SGA_Expenses", "sga expense"),
    ("Selling_General_Admin", "selling general administrative"),
    ("Adj_EBITDA", "adjusted ebitda"),
    ("YTD_Revenue", "ytd revenue"),
    ("Forecast_Opex", "forecast opex"),
    ("Retained_Earnings", "retained earnings"),
    ("Operating_Income", "operating income"),
    ("Total_Taxes", "total tax"),
    ("Dividends", "dividend"),
    ("Other_Income", "other income"),
    ("Amortization", "amortization"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_unknown_header_stays_unresolved() -> None:
    result = load_lexicon().resolve("Mystery_Column")
    assert result.resolved is False
    assert result.unresolved == ("mystery", "column")


def test_vocabulary_loads_without_collisions() -> None:
    assert load_lexicon().resolve("gross profit").resolved is True
