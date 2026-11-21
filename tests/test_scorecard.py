"""Workbook risk scorecard: weights, bands, reasons, and pipeline signals."""

from uuid import UUID

import pytest

from archon.pipeline import run_audit
from archon.risk.scorecard import load_scorecard, score_workbook, signals

ZERO = dict.fromkeys(signals(), 0)


def _score(**counts):
    return score_workbook({**ZERO, **counts})


def test_weights_follow_the_dossier():
    weights = {k: a["weight"] for k, a in load_scorecard()["axes"].items()}
    assert weights == {
        "structural_fragility": 30, "opaque_vba": 30, "lineage": 25, "governance": 15,
    }


def test_clean_workbook_scores_zero_and_low():
    card = _score()
    assert (card["score"], card["band"]) == (0, "Low")
    assert all(a["contributions"] == [] for a in card["axes"])


def test_every_point_has_a_reason():
    card = _score(override_bug=2, very_hidden_sheet=1)
    structural = card["axes"][0]
    assert structural["contributions"] == [
        {"signal": "override_bug", "label": "hardcoded values typed over a copied formula",
         "count": 2, "points": 50},
    ]
    # 30% of 50 + 25% of 25 = 21.25
    assert card["score"] == 21


def test_axis_is_capped_at_100_and_says_so():
    card = _score(override_bug=10)
    assert card["axes"][0]["score"] == 100
    assert card["axes"][0]["capped"] is True
    assert card["score"] == 30


@pytest.mark.parametrize(
    ("counts", "band"),
    [({"override_bug": 4, "vba_dynamic_write": 7, "external_link": 5, "unexplained_pct": 100}, "Extreme"),
     ({"override_bug": 4, "vba_dynamic_write": 7}, "High"),
     ({"override_bug": 4}, "Moderate")],
)
def test_bands(counts, band):
    assert _score(**counts)["band"] == band


def test_unknown_or_missing_signals_are_rejected():
    with pytest.raises(ValueError):
        score_workbook({"override_bug": 1})
    with pytest.raises(ValueError):
        score_workbook({**ZERO, "made_up": 1})


def test_pipeline_feeds_vba_and_sheet_signals():
    rows = [("S", "A1", "Amount"), ("S", "A2", "5"), ("S", "B2", "=A2*2"), ("T", "A1", "=S!B2")]
    code = (
        "Sub Run()\n On Error Resume Next\n Worksheets(\"S\").Range(\"A2\").Value = 1\n"
        " Range(\"A\" & i).Value = 2\nEnd Sub"
    )
    out = run_audit(rows, UUID(int=3), vba=[{"module": "M", "code": code}],
                    context={"very_hidden_sheets": 1, "hidden_sheets": 0, "external_links": 2})
    found = {c["signal"]: c["count"] for a in out["scorecard"]["axes"] for c in a["contributions"]}
    assert found["vba_error_suppression"] == 1
    assert found["vba_write"] == 1
    assert found["vba_dynamic_write"] == 1
    assert found["very_hidden_sheet"] == 1
    assert found["external_link"] == 2
    assert found["cross_sheet_link"] == 1
    assert found["flagged_block_score"] == 10  # =A2*2 types the number 2 into a formula
