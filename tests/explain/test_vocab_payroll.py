"""Payroll vocabulary: real-world headers must resolve to exact phrases."""

import pytest

from archon.explain.lexicon import load_lexicon

CASES = [
    ("Basic_Salary", "basic salary"),
    ("HRA", "hra"),
    ("DA", "da"),
    ("PF_Employer", "pf employer"),
    ("ESI_Employee", "esi employee"),
    ("Net_Pay", "net pay"),
    ("Overtime_Hours", "overtime hour"),
    ("OT_Hours", "overtime hour"),
    ("Gratuity", "gratuity"),
    ("Leave_Encashment", "leave encashment"),
    ("Provident_Fund", "provident fund"),
    ("Health_Insurance", "health insurance"),
    ("Pension", "pension"),
    ("Wages", "wage"),
    ("Stipend", "stipend"),
    ("Reimbursements", "reimbursement"),
    ("Arrears", "arrear"),
    ("Severance", "severance"),
    ("Cost_to_Company", "cost to company"),
    ("CTC", "ctc"),
    ("Take_Home", "take home"),
    ("Professional_Tax", "professional tax"),
    ("Employer_Contribution", "employer contribution"),
    ("Leave_Balance", "leave balance"),
    ("Notice_Period", "notice period"),
    ("Variable_Pay", "variable pay"),
    ("Pay_Grade", "pay grade"),
    ("Days_Worked", "day worked"),
    ("Emp_Salary", "employee salary"),
    ("Allowances", "allowance"),
    ("Special_Allowance", "special allowance"),
    ("Attendance", "attendance"),
    ("Headcount", "headcount"),
]


@pytest.mark.parametrize(("header", "phrase"), CASES)
def test_header_resolves(header: str, phrase: str) -> None:
    result = load_lexicon().resolve(header)
    assert result.resolved is True
    assert result.unresolved == ()
    assert result.phrase == phrase


def test_existing_terms_unchanged() -> None:
    assert load_lexicon().resolve("Salary").phrase == "salary"
    assert load_lexicon().resolve("Sal").phrase == "salary"
    assert load_lexicon().resolve("Bonus").phrase == "bonus"
    assert load_lexicon().resolve("Payroll").phrase == "payroll"


def test_mixed_known_and_unknown_is_unresolved() -> None:
    result = load_lexicon().resolve("Gratuity_Zorp")
    assert result.resolved is False
    assert result.unresolved == ("zorp",)
