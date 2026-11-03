"""Composer: explanation records -> Contract F section tree (deterministic)."""

from collections.abc import Iterable
from uuid import UUID

from archon.contracts.explain import ExplanationRecord
from archon.contracts.report import ReportDocument, ReportEntry, ReportSection
from archon.explain.risk import RiskResult, score_record


def _entry(record: ExplanationRecord, risk: RiskResult) -> ReportEntry:
    return ReportEntry(
        node_id=record.node_id,
        status=record.status,
        plain_english=record.plain_english,
        risk_score=risk.score,
        risk_flags=list(risk.flags),
    )


def compose_report(
    workbook_id: UUID, records: Iterable[ExplanationRecord]
) -> ReportDocument:
    ordered = sorted(records, key=lambda r: r.node_id)
    ids = [r.node_id for r in ordered]
    for first, second in zip(ids, ids[1:], strict=False):
        if first == second:
            raise ValueError(f"duplicate node_id: {first}")

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
