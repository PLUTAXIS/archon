"""Tests for archon.formula.parser."""

import unittest

from archon.formula.ast import BinOp, Func, Lit, Ref, UnaryOp
from archon.formula.parser import ParseError, parse


def ref(text, sheet=None, absolute=(False, False)):
    """Build the Ref node the parser is expected to produce."""
    return Ref(sheet=sheet, r1c1=text, absolute=absolute)


class TestLiterals(unittest.TestCase):
    """Literal values."""

    def test_number(self):
        """A number becomes a float Lit."""
        self.assertEqual(parse("=42"), Lit(value=42.0))

    def test_decimal(self):
        """A decimal number keeps its fraction."""
        self.assertEqual(parse("=3.5"), Lit(value=3.5))

    def test_string(self):
        """A string literal drops its quotes."""
        self.assertEqual(parse('="abc"'), Lit(value="abc"))

    def test_string_escaped_quote(self):
        """A doubled quote inside a string becomes one quote."""
        self.assertEqual(parse('="a""b"'), Lit(value='a"b'))

    def test_boolean(self):
        """TRUE and FALSE become bool Lits."""
        self.assertEqual(parse("=TRUE"), Lit(value=True))
        self.assertEqual(parse("=FALSE"), Lit(value=False))


class TestRefs(unittest.TestCase):
    """Cell references and ranges."""

    def test_simple_ref(self):
        """A relative cell reference has no absolute flags."""
        self.assertEqual(parse("=A1"), ref("A1"))

    def test_fully_absolute_ref(self):
        """$A$1 is absolute in both directions."""
        self.assertEqual(parse("=$A$1"), ref("$A$1", absolute=(True, True)))

    def test_row_absolute_ref(self):
        """A$1 is row-absolute only."""
        self.assertEqual(parse("=A$1"), ref("A$1", absolute=(True, False)))

    def test_col_absolute_ref(self):
        """$A1 is column-absolute only."""
        self.assertEqual(parse("=$A1"), ref("$A1", absolute=(False, True)))

    def test_range(self):
        """A1:B2 is a ':' BinOp of two refs."""
        self.assertEqual(
            parse("=A1:B2"), BinOp(op=":", left=ref("A1"), right=ref("B2"))
        )

    def test_whole_column(self):
        """A:A is a range of two column refs."""
        self.assertEqual(
            parse("=A:A"), BinOp(op=":", left=ref("A"), right=ref("A"))
        )

    def test_whole_row(self):
        """1:3 is a range of two row refs."""
        self.assertEqual(
            parse("=1:3"), BinOp(op=":", left=ref("1"), right=ref("3"))
        )

    def test_sheet_ref(self):
        """Sheet1!A1 carries the sheet name."""
        self.assertEqual(parse("=Sheet1\x21A1"), ref("A1", sheet="Sheet1"))

    def test_quoted_sheet_ref(self):
        """A quoted sheet name is unquoted."""
        self.assertEqual(
            parse("='My Sheet'\x21A1"), ref("A1", sheet="My Sheet")
        )

    def test_defined_name(self):
        """A bare name is kept verbatim as a Ref (documented gap)."""
        self.assertEqual(parse("=MyRange"), ref("MyRange"))


class TestFunctions(unittest.TestCase):
    """Function calls."""

    def test_function_with_args(self):
        """Arguments are parsed in order."""
        self.assertEqual(
            parse("=SUM(A1,2)"),
            Func(name="SUM", args=(ref("A1"), Lit(value=2.0))),
        )

    def test_function_with_range(self):
        """A range is a single argument."""
        self.assertEqual(
            parse("=SUM(A1:A3)"),
            Func(
                name="SUM",
                args=(BinOp(op=":", left=ref("A1"), right=ref("A3")),),
            ),
        )

    def test_function_no_args(self):
        """A call with no arguments has an empty args tuple."""
        self.assertEqual(parse("=NOW()"), Func(name="NOW", args=()))

    def test_nested_functions(self):
        """Calls can nest."""
        self.assertEqual(
            parse("=IF(A1,SUM(B1,B2),0)"),
            Func(
                name="IF",
                args=(
                    ref("A1"),
                    Func(name="SUM", args=(ref("B1"), ref("B2"))),
                    Lit(value=0.0),
                ),
            ),
        )


class TestPrecedence(unittest.TestCase):
    """Excel's operator precedence, including its quirks."""

    def test_mul_before_add(self):
        """'*' binds tighter than '+'."""
        self.assertEqual(
            parse("=1+2*3"),
            BinOp(
                op="+",
                left=Lit(value=1.0),
                right=BinOp(op="*", left=Lit(value=2.0), right=Lit(value=3.0)),
            ),
        )

    def test_add_left_associative(self):
        """'-' chains left to right."""
        self.assertEqual(
            parse("=1-2-3"),
            BinOp(
                op="-",
                left=BinOp(op="-", left=Lit(value=1.0), right=Lit(value=2.0)),
                right=Lit(value=3.0),
            ),
        )

    def test_parens_override(self):
        """Parentheses override precedence and leave no node."""
        self.assertEqual(
            parse("=(1+2)*3"),
            BinOp(
                op="*",
                left=BinOp(op="+", left=Lit(value=1.0), right=Lit(value=2.0)),
                right=Lit(value=3.0),
            ),
        )

    def test_unary_minus_binds_tighter_than_power(self):
        """-2^2 is (-2)^2, as in Excel."""
        self.assertEqual(
            parse("=-2^2"),
            BinOp(
                op="^",
                left=UnaryOp(op="-", operand=Lit(value=2.0)),
                right=Lit(value=2.0),
            ),
        )

    def test_percent_looser_than_unary(self):
        """-5% is (-5)%."""
        self.assertEqual(
            parse("=-5%"),
            UnaryOp(
                op="%",
                operand=UnaryOp(op="-", operand=Lit(value=5.0)),
                postfix=True,
            ),
        )

    def test_percent_tighter_than_power(self):
        """-5%^2 is ((-5)%)^2."""
        self.assertEqual(
            parse("=-5%^2"),
            BinOp(
                op="^",
                left=UnaryOp(
                    op="%",
                    operand=UnaryOp(op="-", operand=Lit(value=5.0)),
                    postfix=True,
                ),
                right=Lit(value=2.0),
            ),
        )

    def test_power_right_associative(self):
        """2^3^2 is 2^(3^2)."""
        self.assertEqual(
            parse("=2^3^2"),
            BinOp(
                op="^",
                left=Lit(value=2.0),
                right=BinOp(op="^", left=Lit(value=3.0), right=Lit(value=2.0)),
            ),
        )

    def test_double_unary(self):
        """--5 nests two unary minus nodes."""
        self.assertEqual(
            parse("=--5"),
            UnaryOp(
                op="-", operand=UnaryOp(op="-", operand=Lit(value=5.0))
            ),
        )

    def test_chained_percent(self):
        """50%% applies '%' twice."""
        self.assertEqual(
            parse("=50%%"),
            UnaryOp(
                op="%",
                operand=UnaryOp(op="%", operand=Lit(value=50.0), postfix=True),
                postfix=True,
            ),
        )

    def test_concat_looser_than_add(self):
        """'&' binds looser than '+'."""
        self.assertEqual(
            parse("=1&2+3"),
            BinOp(
                op="&",
                left=Lit(value=1.0),
                right=BinOp(op="+", left=Lit(value=2.0), right=Lit(value=3.0)),
            ),
        )

    def test_comparison_loosest(self):
        """Comparison binds looser than '&'."""
        self.assertEqual(
            parse("=1&2=3"),
            BinOp(
                op="=",
                left=BinOp(op="&", left=Lit(value=1.0), right=Lit(value=2.0)),
                right=Lit(value=3.0),
            ),
        )

    def test_two_char_comparisons(self):
        """<=, >= and <> parse as single operators."""
        for op in ("<=", ">=", "<>"):
            self.assertEqual(
                parse("=A1" + op + "B1"),
                BinOp(op=op, left=ref("A1"), right=ref("B1")),
            )


class TestSheetQualifiedRanges(unittest.TestCase):
    """Sheet scope on range corners."""

    def test_sheet_propagates_to_unqualified_corner(self):
        """Sheet1!A:A gives both corners sheet='Sheet1'."""
        self.assertEqual(
            parse("=Sheet1\x21A:A"),
            BinOp(op=":", left=ref("A", sheet="Sheet1"), right=ref("A", sheet="Sheet1")),
        )

    def test_explicit_sheet_on_second_corner_kept(self):
        """Sheet1!A1:Sheet2!B2 keeps each corner's own sheet."""
        self.assertEqual(
            parse("=Sheet1\x21A1:Sheet2\x21B2"),
            BinOp(op=":", left=ref("A1", sheet="Sheet1"), right=ref("B2", sheet="Sheet2")),
        )


class TestSheetQualifiedNames(unittest.TestCase):
    """Defined names qualified by a sheet."""

    def test_unquoted_sheet_defined_name(self):
        """Sheet1!MyRange keeps the sheet and the raw name."""
        self.assertEqual(
            parse("=Sheet1\x21MyRange"), ref("MyRange", sheet="Sheet1")
        )

    def test_quoted_sheet_defined_name(self):
        """A quoted sheet name works with a defined name too."""
        self.assertEqual(
            parse("='My Sheet'\x21MyRange"), ref("MyRange", sheet="My Sheet")
        )


class TestArrays(unittest.TestCase):
    """Array literals (synthetic ARRAY / ARRAY_ROW funcs)."""

    def test_array_literal(self):
        """Commas separate columns, semicolons separate rows."""
        self.assertEqual(
            parse("={1,2;3,4}"),
            Func(
                name="ARRAY",
                args=(
                    Func(name="ARRAY_ROW", args=(Lit(value=1.0), Lit(value=2.0))),
                    Func(name="ARRAY_ROW", args=(Lit(value=3.0), Lit(value=4.0))),
                ),
            ),
        )


class TestErrors(unittest.TestCase):
    """Malformed formulas raise ParseError."""

    def test_unexpected_token(self):
        """A stray ')' is rejected."""
        with self.assertRaises(ParseError):
            parse("=)")

    def test_missing_close_paren(self):
        """An unclosed '(' is rejected."""
        with self.assertRaises(ParseError):
            parse("=(1+2")

    def test_trailing_tokens(self):
        """Leftover tokens after a full expression are rejected."""
        with self.assertRaises(ParseError):
            parse("=1 2")

    def test_dangling_operator(self):
        """An operator with no right side is rejected."""
        with self.assertRaises(ParseError):
            parse("=1+")


if __name__ == "__main__":
    unittest.main()
