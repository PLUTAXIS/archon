"""The parity tolerance policy: what counts as "matching" between Excel's
own result and the transpiled Python/codegen result for one formula.

This is a deliberate, written-down decision, not an accident discovered
under deadline pressure. Per the brief: Excel and Python legitimately
disagree on floating-point arithmetic, date serials, and rounding, and a
mismatch from one of those sources is nobody's bug. This module is the
single place that decision lives, so it can be defended in the parity
certificate's footnote rather than improvised per-file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

# Excel's day 1 is 1900-01-01. Excel also believes 1900 was a leap year
# (it wasn't), so it has a fictitious serial 60 = "1900-02-29". Every real
# serial from 61 onward is therefore one higher than a correct Gregorian
# count would give. This is load-bearing: replicate the bug, don't "fix"
# it, or converted dates will be off by exactly one day from what Excel
# itself shows for any date on or after 1900-03-01.
_EXCEL_EPOCH = date(1899, 12, 31)  # serial 1 == this date + 1 day == 1900-01-01
_LEAP_BUG_SERIAL = 60  # the fictitious "1900-02-29"


@dataclass(frozen=True, slots=True)
class TolerancePolicy:
    """The full set of rules for comparing one Excel value to one Python value.

    float_relative: relative tolerance for numeric comparison (see
        values_match). 1e-9 absorbs ordinary floating-point noise without
        hiding a real calculation error.
    date_mode: identifies which date-serial convention is in force.
        Only "serial_1900_with_leap_bug" is currently implemented, which
        is Excel's own default and what virtually every client file uses.
    rounding: identifies which rounding convention ROUND uses. Only
        "excel_half_up" is currently implemented (half away from zero,
        not Python's builtin banker's rounding).
    empty_cell: identifies how a blank cell behaves. Only
        "zero_in_arithmetic_blank_in_concat" is implemented -- an empty
        cell is 0 in arithmetic context but "" in concatenation context,
        matching Excel's own behavior.
    """

    float_relative: float = 1e-9
    date_mode: str = "serial_1900_with_leap_bug"
    rounding: str = "excel_half_up"
    empty_cell: str = "zero_in_arithmetic_blank_in_concat"


DEFAULT_POLICY = TolerancePolicy()


def values_match(excel_value: object, python_value: object, policy: TolerancePolicy = DEFAULT_POLICY) -> bool:
    """Decide whether one (excel_value, python_value) pair counts as a match.

    Numeric values (int/float, excluding bool) are compared with
    math.isclose using policy.float_relative as rel_tol, plus the same
    value as abs_tol so values near zero -- where a relative tolerance
    alone is meaningless -- still compare sanely. Booleans are compared
    for exact identity, not as 0/1 numbers, because Excel's TRUE/FALSE
    is a distinct type from a number even though it coerces to one in
    arithmetic. Everything else (strings, Excel error values like
    "#DIV/0!", None for blanks) is compared for exact equality.
    """
    if isinstance(excel_value, bool) or isinstance(python_value, bool):
        return excel_value is python_value
    if isinstance(excel_value, (int, float)) and isinstance(python_value, (int, float)):
        return math.isclose(
            excel_value,
            python_value,
            rel_tol=policy.float_relative,
            abs_tol=policy.float_relative,
        )
    return excel_value == python_value


def excel_serial_to_date(serial: int, policy: TolerancePolicy = DEFAULT_POLICY) -> date:
    """Convert an Excel date serial number to a real calendar date.

    Replicates Excel's 1900 leap-year bug: a serial of 60 or above is
    treated as one day "ahead" of a true Gregorian count, because Excel
    believes a 1900-02-29 existed between serial 59 (1900-02-28) and
    serial 61 (1900-03-01); serial 60 itself has no real calendar
    meaning and maps to the same date as serial 59. Only
    policy.date_mode == "serial_1900_with_leap_bug" is currently
    supported.
    """
    if policy.date_mode != "serial_1900_with_leap_bug":
        raise NotImplementedError(f"Unsupported date_mode: {policy.date_mode!r}")
    effective = serial if serial < _LEAP_BUG_SERIAL else serial - 1
    return _EXCEL_EPOCH + timedelta(days=effective)


def date_to_excel_serial(d: date, policy: TolerancePolicy = DEFAULT_POLICY) -> int:
    """Inverse of excel_serial_to_date: a real calendar date to an Excel serial."""
    if policy.date_mode != "serial_1900_with_leap_bug":
        raise NotImplementedError(f"Unsupported date_mode: {policy.date_mode!r}")
    effective = (d - _EXCEL_EPOCH).days
    return effective if effective < _LEAP_BUG_SERIAL else effective + 1


def coerce_empty(value: object, context: str, policy: TolerancePolicy = DEFAULT_POLICY) -> object:
    """Resolve a blank cell (None) to Excel's context-dependent empty value.

    context must be "arithmetic" (empty behaves as 0) or "concat" (empty
    behaves as ""). A non-None value passes through unchanged. Only
    policy.empty_cell == "zero_in_arithmetic_blank_in_concat" is
    currently supported.
    """
    if policy.empty_cell != "zero_in_arithmetic_blank_in_concat":
        raise NotImplementedError(f"Unsupported empty_cell policy: {policy.empty_cell!r}")
    if value is not None:
        return value
    if context == "arithmetic":
        return 0
    if context == "concat":
        return ""
    raise ValueError(f"context must be 'arithmetic' or 'concat', got {context!r}")
