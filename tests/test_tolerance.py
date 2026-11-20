"""Tests for archon.parity.tolerance."""

import unittest
from datetime import date

from archon.parity.tolerance import (
    DEFAULT_POLICY,
    coerce_empty,
    date_to_excel_serial,
    excel_serial_to_date,
    values_match,
)


class TestValuesMatch(unittest.TestCase):
    def test_exact_numeric_match(self):
        self.assertTrue(values_match(3.0, 3.0))

    def test_numeric_within_relative_tolerance(self):
        self.assertTrue(values_match(1.0, 1.0 + 1e-10))

    def test_numeric_outside_tolerance_does_not_match(self):
        self.assertFalse(values_match(1.0, 1.1))

    def test_near_zero_uses_absolute_tolerance(self):
        self.assertTrue(values_match(0.0, 1e-10))

    def test_int_and_float_compare_numerically(self):
        self.assertTrue(values_match(3, 3.0))

    def test_boolean_is_not_treated_as_a_number(self):
        self.assertFalse(values_match(True, 1))
        self.assertFalse(values_match(1, True))

    def test_boolean_exact_match(self):
        self.assertTrue(values_match(True, True))
        self.assertFalse(values_match(True, False))

    def test_string_exact_match(self):
        self.assertTrue(values_match("hello", "hello"))
        self.assertFalse(values_match("hello", "Hello"))

    def test_excel_error_value_compared_as_string(self):
        self.assertTrue(values_match("#DIV/0!", "#DIV/0!"))
        self.assertFalse(values_match("#DIV/0!", "#N/A"))

    def test_none_matches_none(self):
        self.assertTrue(values_match(None, None))


class TestExcelDateSerials(unittest.TestCase):
    def test_serial_one_is_jan_1_1900(self):
        self.assertEqual(excel_serial_to_date(1), date(1900, 1, 1))

    def test_known_serial_before_leap_bug_cutoff(self):
        self.assertEqual(excel_serial_to_date(59), date(1900, 2, 28))

    def test_fictitious_leap_day_serial_has_no_real_date_but_does_not_crash(self):
        self.assertEqual(excel_serial_to_date(60), date(1900, 2, 28))

    def test_known_serial_after_leap_bug_cutoff(self):
        self.assertEqual(excel_serial_to_date(61), date(1900, 3, 1))

    def test_well_known_modern_date(self):
        self.assertEqual(excel_serial_to_date(45292), date(2024, 1, 1))

    def test_round_trip_before_cutoff(self):
        d = date(1900, 1, 15)
        self.assertEqual(excel_serial_to_date(date_to_excel_serial(d)), d)

    def test_round_trip_after_cutoff(self):
        d = date(2024, 1, 1)
        self.assertEqual(excel_serial_to_date(date_to_excel_serial(d)), d)

    def test_round_trip_at_cutoff_boundary(self):
        d = date(1900, 3, 1)
        self.assertEqual(excel_serial_to_date(date_to_excel_serial(d)), d)


class TestCoerceEmpty(unittest.TestCase):
    def test_none_in_arithmetic_is_zero(self):
        self.assertEqual(coerce_empty(None, "arithmetic"), 0)

    def test_none_in_concat_is_empty_string(self):
        self.assertEqual(coerce_empty(None, "concat"), "")

    def test_non_none_passes_through_unchanged(self):
        self.assertEqual(coerce_empty(5.0, "arithmetic"), 5.0)
        self.assertEqual(coerce_empty("x", "concat"), "x")

    def test_invalid_context_raises(self):
        with self.assertRaises(ValueError):
            coerce_empty(None, "bogus")


class TestDefaultPolicy(unittest.TestCase):
    def test_default_policy_values(self):
        self.assertEqual(DEFAULT_POLICY.float_relative, 1e-9)
        self.assertEqual(DEFAULT_POLICY.date_mode, "serial_1900_with_leap_bug")
        self.assertEqual(DEFAULT_POLICY.rounding, "excel_half_up")
        self.assertEqual(DEFAULT_POLICY.empty_cell, "zero_in_arithmetic_blank_in_concat")


if __name__ == "__main__":
    unittest.main()
