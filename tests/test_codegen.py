"""Tests for archon.transpile.codegen and archon.transpile.runtime."""

import unittest

import archon.transpile.runtime as rt
from archon.formula.parser import parse
from archon.transpile.codegen import (
    CodegenError,
    generate_expr,
    generate_python_function,
)


class FakeCtx:
    """A minimal runtime context for tests: a dict of (sheet, addr) -> value,
    with get_range() supporting simple same-column numeric-row ranges only
    (enough for these tests; not a real spreadsheet engine)."""

    def __init__(self, data):
        self.data = data

    def get(self, sheet, addr):
        return self.data.get((sheet, addr))

    def get_range(self, sheet, start, end):
        col = "".join(c for c in start if c.isalpha())
        srow = int("".join(c for c in start if c.isdigit()))
        erow = int("".join(c for c in end if c.isdigit()))
        return [self.data.get((sheet, f"{col}{r}")) for r in range(srow, erow + 1)]


def run(formula: str, sheet: str = "Sheet1", data: dict | None = None):
    """Parse, generate, and evaluate a formula against a FakeCtx in one step."""
    node = parse(formula)
    code = generate_expr(node, sheet)
    ctx = FakeCtx(data or {})
    return eval(code, {"rt": rt}, {"ctx": ctx})


class TestLiteralsAndArithmetic(unittest.TestCase):
    def test_number_literal(self):
        self.assertEqual(run("=42"), 42.0)

    def test_string_literal(self):
        self.assertEqual(run('="hello"'), "hello")

    def test_boolean_literal(self):
        self.assertEqual(run("=TRUE"), True)

    def test_simple_addition(self):
        self.assertEqual(run("=1+2"), 3.0)

    def test_precedence_mul_before_add(self):
        self.assertEqual(run("=1+2*3"), 7.0)

    def test_parens_override_precedence(self):
        self.assertEqual(run("=(1+2)*3"), 9.0)


class TestExcelPrecedenceCorrectness(unittest.TestCase):
    def test_unary_minus_binds_tighter_than_exponent(self):
        self.assertEqual(run("=-2^2"), 4.0)

    def test_exponent_is_left_associative(self):
        self.assertEqual(run("=2^3^2"), 64.0)

    def test_percent_binds_looser_than_unary_minus(self):
        self.assertAlmostEqual(run("=-5%"), -0.05)

    def test_percent_tighter_than_exponent(self):
        self.assertAlmostEqual(run("=-5%^2"), 0.0025)


class TestRefsAndRanges(unittest.TestCase):
    def test_simple_ref_lookup(self):
        self.assertEqual(run("=A1", data={("Sheet1", "A1"): 7.0}), 7.0)

    def test_cross_sheet_ref(self):
        self.assertEqual(
            run("=Sheet2!A1", data={("Sheet2", "A1"): 9.0}), 9.0
        )

    def test_sum_over_range_plus_scalar(self):
        data = {
            ("Sheet1", "A1"): 1.0,
            ("Sheet1", "A2"): 2.0,
            ("Sheet1", "A3"): 3.0,
            ("Sheet1", "B1"): 10.0,
        }
        self.assertEqual(run("=SUM(A1:A3)+B1", data=data), 16.0)

    def test_range_argument_rejected_for_non_range_aware_function(self):
        node = parse("=IF(A1:A3,1,0)")
        with self.assertRaises(CodegenError):
            generate_expr(node, "Sheet1")

    def test_cross_sheet_range_rejected(self):
        from archon.formula.ast import BinOp, Ref

        bad_range = BinOp(
            op=":",
            left=Ref(sheet="Sheet1", r1c1="A1", absolute=(False, False)),
            right=Ref(sheet="Sheet2", r1c1="A3", absolute=(False, False)),
        )
        with self.assertRaises(CodegenError):
            generate_expr(bad_range, "Sheet1")


class TestFunctions(unittest.TestCase):
    def test_if_true_branch(self):
        self.assertEqual(
            run('=IF(A1>0,"yes","no")', data={("Sheet1", "A1"): 5.0}), "yes"
        )

    def test_if_false_branch(self):
        self.assertEqual(
            run('=IF(A1>0,"yes","no")', data={("Sheet1", "A1"): -5.0}), "no"
        )

    def test_round_half_away_from_zero_like_excel(self):
        self.assertEqual(run("=ROUND(2.5,0)"), 3.0)
        self.assertEqual(run("=ROUND(-2.5,0)"), -3.0)

    def test_concatenate(self):
        self.assertEqual(run('=CONCATENATE("a","b","c")'), "abc")

    def test_and_or_not(self):
        self.assertEqual(run("=AND(TRUE,TRUE)"), True)
        self.assertEqual(run("=OR(FALSE,TRUE)"), True)
        self.assertEqual(run("=NOT(TRUE)"), False)

    def test_unmapped_function_raises_codegen_error(self):
        node = parse("=VLOOKUP(A1,B1:C10,2,FALSE)")
        with self.assertRaises(CodegenError):
            generate_expr(node, "Sheet1")

    def test_average_of_no_numeric_values_raises_zero_division(self):
        node = parse('=AVERAGE("a","b")')
        code = generate_expr(node, "Sheet1")
        with self.assertRaises(ZeroDivisionError):
            eval(code, {"rt": rt}, {"ctx": FakeCtx({})})


class TestArrayLiteralsRejected(unittest.TestCase):
    def test_array_literal_raises_codegen_error(self):
        node = parse("={1,2;3,4}")
        with self.assertRaises(CodegenError):
            generate_expr(node, "Sheet1")


class TestGeneratePythonFunction(unittest.TestCase):
    def test_wraps_expression_in_callable_function(self):
        node = parse("=1+2")
        src = generate_python_function(node, "Sheet1", func_name="my_formula")
        self.assertIn("def my_formula(ctx):", src)
        namespace = {"rt": rt}
        exec(src, namespace)
        self.assertEqual(namespace["my_formula"](FakeCtx({})), 3.0)


class TestRuntimeFunctionsDirectly(unittest.TestCase):
    def test_xl_sum_flattens_scalars_and_lists(self):
        self.assertEqual(rt.xl_sum(1.0, [2.0, 3.0], 4.0), 10.0)

    def test_xl_sum_ignores_text_and_none(self):
        self.assertEqual(rt.xl_sum(1.0, "text", None, 2.0), 3.0)

    def test_xl_sum_ignores_booleans(self):
        self.assertEqual(rt.xl_sum(1.0, True, False, 2.0), 3.0)

    def test_xl_max_min_of_empty_is_zero(self):
        self.assertEqual(rt.xl_max(), 0.0)
        self.assertEqual(rt.xl_min(), 0.0)

    def test_xl_average_empty_raises(self):
        with self.assertRaises(ZeroDivisionError):
            rt.xl_average()

    def test_xl_round_matches_excel_half_up_not_bankers_rounding(self):
        self.assertEqual(rt.xl_round(0.5, 0), 1.0)
        self.assertEqual(rt.xl_round(1.5, 0), 2.0)
        self.assertEqual(rt.xl_round(2.5, 0), 3.0)
        self.assertEqual(round(2.5), 2)


if __name__ == "__main__":
    unittest.main()
