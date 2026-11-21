"""Composer: ExplanationRecords -> Contract F section tree."""

from uuid import UUID

import pytest

from archon.contracts.explain import ExplanationRecord
from archon.contracts.report import ReportDocument
from archon.explain.composer import compose_report
from archon.explain.formula_ast import parse_mock_formula
from archon.explain.matcher import match_formula
from archon.explain.unmatched import ShapeCount

WB = UUID("5b0f1c1e-8f4e-4c55-9d0e-3c1b2a7d9e11")


def _rec(node_id: str, formula: str, cell: str = "G2") -> ExplanationRecord:
    return match_formula(node_id, cell, parse_mock_formula(formula))


def _records() -> list[ExplanationRecord]:
    return [
        _rec("n3", "=MIRR(A1:A10)"),
        _rec("n1", "=E2*F2"),
        _rec("n4", "=NOW()"),
        _rec("n2", "=IFERROR(B2/C2,0)"),
    ]


def _by_kind(doc: ReportDocument) -> dict[str, list[str]]:
    return {s.kind: [e.node_id for e in s.entries] for s in doc.sections}


def test_section_order_and_kinds() -> None:
    doc = compose_report(WB, _records())
    assert [s.kind for s in doc.sections] == [
        "explanations",
        "risk",
        "unverified_appendix",
    ]
    assert [s.section_id for s in doc.sections] == [
        "explanations",
        "risk",
        "unverified_appendix",
    ]


def test_explanations_hold_matched_only_sorted_by_node_id() -> None:
    doc = compose_report(WB, _records())
    assert _by_kind(doc)["explanations"] == ["n1", "n2", "n4"]


def test_risk_section_sorted_by_score_desc_then_node_id() -> None:
    doc = compose_report(WB, _records())
    # n2 error=15, n4 volatile=15; n1 zero and n3 unverified are excluded
    # (n3 is listed in the unverified appendix instead)
    assert _by_kind(doc)["risk"] == ["n2", "n4"]


def test_unverified_appendix_holds_unverified_only() -> None:
    doc = compose_report(WB, _records())
    assert _by_kind(doc)["unverified_appendix"] == ["n3"]
    entry = doc.sections[2].entries[0]
    assert entry.plain_english is None
    assert entry.risk_flags == ["UNVERIFIED_FORMULA"]
    assert entry.risk_score == 20


def test_entry_carries_text_score_and_flags() -> None:
    doc = compose_report(WB, [_rec("n4", "=NOW()")])
    entry = doc.sections[0].entries[0]
    assert entry.plain_english == (
        "Current date and time; recalculates on every change."
    )
    assert entry.risk_score == 15
    assert entry.risk_flags == ["VOLATILE_FUNCTION"]


def test_input_order_does_not_matter() -> None:
    forward = compose_report(WB, _records())
    backward = compose_report(WB, list(reversed(_records())))
    assert forward.model_dump_json() == backward.model_dump_json()


def test_duplicate_node_id_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate node_id"):
        compose_report(WB, [_rec("n1", "=E2*F2"), _rec("n1", "=NOW()")])


def test_empty_input_still_has_all_sections() -> None:
    doc = compose_report(WB, [])
    assert [s.kind for s in doc.sections] == [
        "explanations",
        "risk",
        "unverified_appendix",
    ]
    assert all(s.entries == [] for s in doc.sections)


def test_round_trips_through_contract() -> None:
    doc = compose_report(WB, _records())
    again = ReportDocument.model_validate_json(doc.model_dump_json())
    assert again == doc


def test_determinism() -> None:
    first = compose_report(WB, _records()).model_dump_json()
    for _ in range(20):
        assert compose_report(WB, _records()).model_dump_json() == first


def test_unmatched_shapes_default_is_empty() -> None:
    assert compose_report(WB, _records()).unmatched_shapes == []


def test_unmatched_shapes_carried_and_ranked() -> None:
    doc = compose_report(
        WB,
        _records(),
        unmatched_shapes=[
            ShapeCount("NPV(<ref>,<ref>)", 1),
            ShapeCount("MIRR(<range>)", 3),
            ShapeCount("IRR(<ref>,<ref>)", 1),
        ],
    )
    assert [(s.shape, s.count) for s in doc.unmatched_shapes] == [
        ("MIRR(<range>)", 3),
        ("IRR(<ref>,<ref>)", 1),
        ("NPV(<ref>,<ref>)", 1),
    ]


def test_unmatched_shapes_duplicate_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate shape"):
        compose_report(
            WB,
            [],
            unmatched_shapes=[ShapeCount("A()", 2), ShapeCount("A()", 1)],
        )
