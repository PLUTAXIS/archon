"""Composer: explanation records -> Contract F section tree (deterministic)."""

from collections.abc import Iterable
from itertools import pairwise
from uuid import UUID

from archon.contracts.explain import ExplanationRecord
from archon.contracts.report import (
    ReportDocument,
    ReportEntry,
    ReportSection,
    UnmatchedShape,
)
from archon.explain.risk import RiskResult, score_record
from archon.explain.unmatched import ShapeCount


def _entry(record: ExplanationRecord, risk: RiskResult) -> ReportEntry:
    """Build one report entry from a record and its risk result."""
    return ReportEntry(
        node_id=record.node_id,
        status=record.status,
        plain_english=record.plain_english,
        risk_score=risk.score,
        risk_flags=list(risk.flags),
    )


def compose_report(
    workbook_id: UUID,
    records: Iterable[ExplanationRecord],
    *,
    unmatched_shapes: Iterable[ShapeCount] = (),
) -> ReportDocument:
    """Compose records into a deterministic three-section report.

    Sections: explanations (matched), risk (score > 0, highest first),
    unverified appendix. Input order never affects output. Raises
    ValueError on duplicate node ids.
    """
    ordered = sorted(records, key=lambda r: r.node_id)
    ids = [r.node_id for r in ordered]
    for first, second in pairwise(ids):
        if first == second:
            raise ValueError(f"duplicate node_id: {first}")

    ranked = sorted(unmatched_shapes, key=lambda u: (-u.count, u.shape))
    seen = [u.shape for u in ranked]
    if len(seen) != len(set(seen)):
        raise ValueError("duplicate shape in unmatched_shapes")

    scored = [(r, score_record(r)) for r in ordered]
    explanations = [_entry(r, s) for r, s in scored if r.status == "matched"]
    appendix = [_entry(r, s) for r, s in scored if r.status == "unverified"]
    risky = sorted(
        (_entry(r, s) for r, s in scored if s.score > 0),
        key=lambda e: (-e.risk_score, e.node_id),
    )

    return ReportDocument(
        schema_version="1.0",
        workbook_id=workbook_id,
        unmatched_shapes=[UnmatchedShape(shape=u.shape, count=u.count) for u in ranked],
        sections=[
            ReportSection(
                section_id="explanations",
                kind="explanations",
                title="Explanations",
                entries=explanations,
                children=[],
            ),
            ReportSection(
                section_id="risk",
                kind="risk",
                title="Risk",
                entries=risky,
                children=[],
            ),
            ReportSection(
                section_id="unverified_appendix",
                kind="unverified_appendix",
                title="Unverified formulas",
                entries=appendix,
                children=[],
            ),
        ],
    )
