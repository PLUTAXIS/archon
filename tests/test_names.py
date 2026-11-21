"""Named ranges and whole-column references."""

from archon.contracts.extract import DefinedName
from archon.names import bound_whole_columns, expand_names, named_cells, reference_names

NAMES = [
    DefinedName(name="TaxRate", scope="workbook", refers_to="Inputs!$B$1"),
    DefinedName(name="RateTable", scope="workbook", refers_to="'Rate Card'!$A$2:$B$9"),
    DefinedName(name="VAT", scope="workbook", refers_to="0.2"),  # a constant: never expanded
    DefinedName(name="Window", scope="workbook", refers_to="OFFSET(A1,0,0,5,1)"),  # dynamic
    DefinedName(name="Local", scope="1", refers_to="Calc!$D$1"),  # only on sheet index 1
]
TABLE = reference_names(NAMES, ["Inputs", "Calc"])


def test_only_plain_references_are_kept():
    assert sorted(TABLE[""]) == ["RATETABLE", "TAXRATE"]
    assert TABLE["Calc"] == {"LOCAL": ("Local", "Calc!$D$1")}


def test_names_are_expanded_case_insensitively():
    assert expand_names("=A2*taxrate", "Calc", TABLE) == "=A2*Inputs!$B$1"
    assert expand_names("=VLOOKUP(A2,RateTable,2,0)", "Calc", TABLE) == (
        "=VLOOKUP(A2,'Rate Card'!$A$2:$B$9,2,0)"
    )


def test_what_must_not_be_rewritten():
    # text literals, function names, sheet names, unknown and constant names
    assert expand_names('="TaxRate"&TaxRate', "Calc", TABLE) == '="TaxRate"&Inputs!$B$1'
    assert expand_names("=TAXRATE(A1)+TaxRate!A1", "Calc", TABLE) == "=TAXRATE(A1)+TaxRate!A1"
    assert expand_names("=A2*VAT+Window", "Calc", TABLE) == "=A2*VAT+Window"


def test_sheet_scoped_names_apply_only_on_their_sheet():
    assert expand_names("=Local*2", "Calc", TABLE) == "=Calc!$D$1*2"
    assert expand_names("=Local*2", "Inputs", TABLE) == "=Local*2"


def test_whole_columns_are_bounded_by_the_used_rows_of_their_sheet():
    last = {"Calc": 500, "Inputs": 12}
    assert bound_whole_columns("=SUM(C:C)", "Calc", last) == "=SUM(C1:C500)"
    assert bound_whole_columns("=SUM(Inputs!$A:$B)", "Calc", last) == "=SUM(Inputs!$A1:$B12)"
    assert bound_whole_columns('="A:B"&SUM(A1:B2)', "Calc", last) == '="A:B"&SUM(A1:B2)'
    assert bound_whole_columns("=SUM(Empty!A:A)", "Calc", last) == "=SUM(Empty!A:A)"


def test_named_cells_for_labels():
    cells = named_cells(TABLE)
    assert cells[("Inputs", "B1")] == "TaxRate"
    assert cells[("Rate Card", "A2:B9")] == "RateTable"
