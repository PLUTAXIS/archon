from archon.formula.kpi_wiring import Cell, audit_formulas

GOOD = "=SUM(A1:A5)"
BAD = "=SUM((A1:A5"   # unbalanced paren -> ParseError


def _cells():
    return [Cell("Sheet1!B1", GOOD), Cell("Sheet1!B2", BAD), Cell("Sheet1!B3", GOOD)]


def test_failures_are_never_dropped():
    r = audit_formulas(_cells(), source="fixture.xlsx")
    assert len(r.parsed) == 2
    assert len(r.failed) == 1
    assert r.failed[0].ref == "Sheet1!B2"


def test_kpi_counts_match_cells():
    r = audit_formulas(_cells(), source="fixture.xlsx")
    assert r.kpi.total == 3
    assert r.kpi.failure_rate == 1 / 3   # property, not method


def test_ci_gate_fixture_meets_target():
    """CI gate: the all-good fixture must pass the <5% target."""
    r = audit_formulas([Cell("Sheet1!B1", GOOD)], source="fixture.xlsx")
    assert r.kpi.meets_target            # property, not method
