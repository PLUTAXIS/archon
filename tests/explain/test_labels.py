"""Business labels from workbook layout, and naming cells in explanations."""

from archon.explain.labels import Labels

ROWS = [
    ("S", "A1", "Revenue model FY26"),  # title: no data directly below it
    ("S", "A3", "Customer"), ("S", "B3", "Price"), ("S", "C3", "Qty"), ("S", "D3", "Amount"),
    ("S", "A4", "Acme"), ("S", "B4", "10"), ("S", "C4", "3"), ("S", "D4", "=B4*C4"),
    ("S", "A5", "Globex"), ("S", "B5", "12"), ("S", "C5", "4"), ("S", "D5", "=B5*C5"),
    ("S", "A7", "Bonus pool"), ("S", "B7", "=SUM(D4:D5)*0.05"),
    ("In", "A1", "FX"), ("In", "A2", "83.2"),
    ("S", "F1", "2026-01-31T00:00:00"), ("S", "F2", "7"),
]
LB = Labels(ROWS)


def test_column_header_skips_title_rows():
    assert LB.cell("S", "B5", prefer_row=False) == "Price"


def test_text_columns_have_no_header_from_their_own_values():
    # "Acme" sits above "Globex", but text below text is data, not a header
    assert LB.cell("S", "A5", prefer_row=False) == "Customer"


def test_one_off_cells_use_their_row_label():
    assert LB.cell("S", "B7", prefer_row=True) == "Bonus pool"
    assert LB.cell("S", "B7", prefer_row=False) == "Price"


def test_dates_as_headers_are_readable():
    assert LB.cell("S", "F2", prefer_row=False) == "2026-01-31"


def test_relabel_names_cells_ranges_and_other_sheets():
    text = "Product of B4 and C4, total of D4:D5, times In!A2."
    assert LB.relabel(text, "S", prefer_row=False) == (
        "Product of Price (B4) and Qty (C4), total of Amount (D4:D5), times FX (In!A2)."
    )


def test_relabel_leaves_unlabelled_and_multi_column_refs_alone():
    assert LB.relabel("Look up B4:C5 then Z99.", "S", prefer_row=False) == (
        "Look up B4:C5 then Z99."
    )


def test_relabel_does_not_touch_parts_of_longer_tokens():
    assert LB.relabel("VLOOKUP(B4) and B4x and XB4", "S", prefer_row=False) == (
        "VLOOKUP(Price (B4)) and B4x and XB4"
    )
