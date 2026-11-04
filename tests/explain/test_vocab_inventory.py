"""Inventory vocabulary: real-world headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Stock_On_Hand", "stock on hand"),
    ("SOH", "soh"),
    ("Reorder_Level", "reorder level"),
    ("Reorder_Point", "reorder point"),
    ("Safety_Stock", "safety stock"),
    ("SKU", "sku"),
    ("SKU_Code", "sku code"),
    ("Lead_Time", "lead time"),
    ("FIFO_Cost", "fifo cost"),
    ("LIFO_Cost", "lifo cost"),
    ("Weighted_Average_Cost", "weighted average cost"),
    ("Days_Inventory", "day inventory"),
    ("DIO", "dio"),
    ("Inventory_Turnover", "inventory turnover"),
    ("Shrinkage", "shrinkage"),
    ("Obsolete_Stock", "obsolete stock"),
    ("Write_Off", "write off"),
    ("Write_Down", "write down"),
    ("Goods_Received", "goods received"),
    ("GRN_Number", "grn number"),
    ("Purchase_Order", "purchase order"),
    ("PO_Quantity", "po quantity"),
    ("Backorder", "backorder"),
    ("Warehouse", "warehouse"),
    ("Warehouse_Location", "warehouse location"),
    ("Bin_Location", "bin location"),
    ("Batch_Number", "batch number"),
    ("Lot_Number", "lot number"),
    ("Expiry_Date", "expiry date"),
    ("Shelf_Life", "shelf life"),
    ("Unit_Cost", "unit cost"),
    ("Cost_Per_Unit", "cost per unit"),
    ("Landed_Cost", "landed cost"),
    ("Freight_Cost", "freight cost"),
    ("Supplier", "supplier"),
    ("Vendor", "vendor"),
    ("Stocks", "stock"),
    ("Items", "item"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_existing_terms_unchanged() -> None:
    assert load_lexicon().resolve("Inventory").phrase == "inventory"
    assert load_lexicon().resolve("Inv").phrase == "inventory"
    assert load_lexicon().resolve("Cost").phrase == "cost"
    assert load_lexicon().resolve("Quantity").phrase == "quantity"
    assert load_lexicon().resolve("Qty").phrase == "quantity"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Shrinkage_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
