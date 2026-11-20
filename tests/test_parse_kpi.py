import json

from archon.parser.kpi import ParseKPI


def test_counts_and_rate():
    kpi = ParseKPI(source="test.xlsx")
    kpi.record_parsed("Sheet1!A1")
    kpi.record_parsed("Sheet1!A2")
    kpi.record_failed("Sheet1!B1", "=LET(x,1,)", "unsupported: LET")
    assert kpi.total == 3
    assert kpi.failure_rate == 1 / 3
    assert not kpi.meets_target


def test_failures_never_silently_dropped():
    kpi = ParseKPI()
    kpi.record_failed("Sheet2!C3", "=FOO(", "unexpected end")
    assert len(kpi.failures) == 1
    assert kpi.failures[0]["ref"] == "Sheet2!C3"


def test_summary_is_deterministic_json(tmp_path):
    kpi = ParseKPI(source="wb")
    kpi.record_parsed("A1")
    kpi.record_failed("B1", "=X(", "bad token")
    out = tmp_path / "kpi.json"
    kpi.write(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kpi"] == "parse_failure_rate"
    assert data["failure_reasons"] == {"bad token": 1}
    out2 = tmp_path / "kpi2.json"
    kpi.write(out2)
    assert out.read_text() == out2.read_text()


def test_zero_formulas_is_safe():
    kpi = ParseKPI()
    assert kpi.failure_rate == 0.0
    assert kpi.meets_target
