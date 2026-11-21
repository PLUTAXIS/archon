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


def test_multi_column_ranges_are_named_by_their_headers():
    assert LB.relabel("Look up B4:C5 then Z99.", "S", prefer_row=False) == (
        "Look up Price / Qty table (B4:C5) then Z99."
    )
    # wide tables shorten to first ... last
    assert LB.relabel("A4:D5", "S", prefer_row=False) == (
        "Customer / … / Amount table (A4:D5)"
    )


def test_ranges_with_an_unlabelled_column_are_left_alone():
    # column G has no header above row 2
    assert LB.relabel("F2:G2", "S", prefer_row=False) == "F2:G2"


def test_relabel_does_not_touch_parts_of_longer_tokens():
    assert LB.relabel("VLOOKUP(B4) and B4x and XB4", "S", prefer_row=False) == (
        "VLOOKUP(Price (B4)) and B4x and XB4"
    )


def test_relabel_never_renames_text_inside_quotes():
    assert LB.relabel("If B4 is “B4”, B4.", "S", prefer_row=False) == (
        "If Price (B4) is “B4”, Price (B4)."
    )


def test_whole_columns_are_named_by_their_header():
    assert LB.relabel("Sum of D:D and B:C.", "S", prefer_row=False) == (
        "Sum of Amount (D:D) and Price / Qty table (B:C)."
    )
