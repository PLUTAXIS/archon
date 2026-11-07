"""Tests for the AST-based A1 -> R1C1 translation in archon.formula.r1c1."""

import unittest

from archon.formula.ast import BinOp, Func, Lit, Ref, UnaryOp
from archon.formula.parser import parse
from archon.formula.r1c1 import to_r1c1_ast


def r(text, sheet=None, absolute=(False, False)):
    """Build the Ref node the parser produces before translation."""
    return Ref(sheet=sheet, r1c1=text, absolute=absolute)


class TestBasicRefs(unittest.TestCase):
    """Relative and absolute single-cell references."""

    def test_relative_ref(self):
        """A relative ref becomes an offset from the anchor."""
        self.assertEqual(
            to_r1c1_ast(parse("=B6*C6"), (6, 4)),
            BinOp(op="*", left=r("RC[-2]"), right=r("RC[-1]")),
        )

    def test_same_cell_ref(self):
        """A reference to the anchor cell itself becomes bare RC."""
        self.assertEqual(to_r1c1_ast(parse("=A1"), (1, 1)), r("RC"))

    def test_fully_absolute_ref(self):
        """$A$1 becomes an absolute R1C1 address regardless of anchor."""
        self.assertEqual(
            to_r1c1_ast(parse("=$A$1"), (6, 4)),
            r("R1C1", absolute=(True, True)),
        )

    def test_row_absolute_ref(self):
        """A$1 keeps the row absolute and the column relative."""
        self.assertEqual(
            to_r1c1_ast(parse("=A$1"), (6, 4)),
            r("R1C[-3]", absolute=(True, False)),
        )

    def test_col_absolute_ref(self):
        """$A1 keeps the column absolute and the row relative."""
        self.assertEqual(
            to_r1c1_ast(parse("=$A1"), (6, 4)),
            r("R[-5]C1", absolute=(False, True)),
        )

    def test_positive_offset(self):
        """A reference below/right of the anchor gets a positive offset."""
        self.assertEqual(to_r1c1_ast(parse("=C8"), (6, 1)), r("R[2]C[2]"))


class TestWholeColumnsAndRows(unittest.TestCase):
    """References with no row or no column component."""

    def test_whole_column(self):
        """A whole-column ref has no R part."""
        self.assertEqual(
            to_r1c1_ast(parse("=A:A"), (6, 4)),
            BinOp(op=":", left=r("C[-3]"), right=r("C[-3]")),
        )

    def test_whole_row(self):
        """A whole-row ref has no C part."""
        self.assertEqual(
            to_r1c1_ast(parse("=1:3"), (6, 4)),
            BinOp(op=":", left=r("R[-5]"), right=r("R[-3]")),
        )


class TestRangesAndSheets(unittest.TestCase):
    """Ranges and sheet-qualified references."""

    def test_range(self):
        """Each corner of a range is translated independently."""
        self.assertEqual(
            to_r1c1_ast(parse("=A1:B2"), (1, 1)),
            BinOp(op=":", left=r("RC"), right=r("R[1]C[1]")),
        )

    def test_sheet_qualified_ref(self):
        """A sheet-qualified ref keeps its sheet name untouched."""
        self.assertEqual(
            to_r1c1_ast(parse("=Sheet1\x21A1"), (6, 4)),
            r("R[-5]C[-3]", sheet="Sheet1"),
        )

    def test_sheet_qualified_range_both_corners(self):
        """A sheet-qualified range translates both corners correctly --
        this is the case the old regex-based to_r1c1() could never fix."""
        self.assertEqual(
            to_r1c1_ast(parse("=Sheet1\x21A1:Sheet1\x21B1"), (1, 1)),
            BinOp(
                op=":",
                left=r("RC", sheet="Sheet1"),
                right=r("RC[1]", sheet="Sheet1"),
            ),
        )


class TestFunctionsAndLiterals(unittest.TestCase):
    """Refs nested inside function calls; literals pass through untouched."""

    def test_ref_inside_function(self):
        """A ref inside SUM(...) is translated in place."""
        self.assertEqual(
            to_r1c1_ast(parse("=SUM(A1:A3)"), (1, 1)),
            Func(
                name="SUM",
                args=(BinOp(op=":", left=r("RC"), right=r("R[2]C")),),
            ),
        )

    def test_literal_unchanged(self):
        """A plain literal has no Ref to translate."""
        self.assertEqual(to_r1c1_ast(parse("=42"), (1, 1)), Lit(value=42.0))

    def test_unary_and_literal(self):
        """Non-Ref nodes are walked but left structurally the same."""
        self.assertEqual(
            to_r1c1_ast(parse("=-A1"), (1, 1)),
            UnaryOp(op="-", operand=r("RC")),
        )


class TestDefinedNameGap(unittest.TestCase):
    """A defined name has no R1C1 form and is passed through unchanged."""

    def test_bare_defined_name_untouched(self):
        """MyRange isn't a cell address, so it's left as raw text."""
        self.assertEqual(to_r1c1_ast(parse("=MyRange"), (6, 4)), r("MyRange"))


if __name__ == "__main__":
    unittest.main()
