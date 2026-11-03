"""Contract F: report section tree (composer -> Deepsikha's previewer)."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

SectionKind = Literal["summary", "explanations", "risk", "bugs", "unverified_appendix"]


class ReportEntry(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    node_id: str
    status: Literal["matched", "unverified"]
    plain_english: str | None
    risk_score: Annotated[int, Field(ge=0, le=100)]
    risk_flags: list[str]

    @model_validator(mode="after")
    def text_must_match_status(self) -> Self:
        if self.status == "matched" and not (self.plain_english or "").strip():
            raise ValueError("matched entries must carry plain_english")
        if self.status == "unverified" and self.plain_english is not None:
            raise ValueError("unverified entries must not carry plain_english")
        return self


class UnmatchedShape(BaseModel):
    """One formula shape the engine could not explain, with its frequency."""

    model_config = {"extra": "forbid", "frozen": True}
    shape: Annotated[str, Field(min_length=1)]
    count: Annotated[int, Field(ge=1)]


class ReportSection(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    section_id: str
    kind: SectionKind
    title: str
    entries: list[ReportEntry]
    children: list["ReportSection"]

    @model_validator(mode="after")
    def appendix_holds_only_unverified(self) -> Self:
        if self.kind == "unverified_appendix" and any(
            e.status != "unverified" for e in self.entries
        ):
            raise ValueError("appendix may contain only unverified entries")
        return self


def _walk(sections: list[ReportSection]) -> list[ReportSection]:
    out: list[ReportSection] = []
    for section in sections:
        out.append(section)
        out.extend(_walk(section.children))
    return out


class ReportDocument(BaseModel):
    model_config = {"extra": "forbid"}
    schema_version: Literal["1.0"]
    workbook_id: UUID
    sections: list[ReportSection]  # no default: explicit, like `exceptions`
    unmatched_shapes: list[UnmatchedShape]  # no default; [] is an explicit claim

    @model_validator(mode="after")
    def structure_rules(self) -> Self:
        everything = _walk(self.sections)
        ids = [s.section_id for s in everything]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate section_id")
        appendices = [s for s in everything if s.kind == "unverified_appendix"]
        if len(appendices) != 1:
            raise ValueError("exactly one unverified_appendix is required")
        shapes = [u.shape for u in self.unmatched_shapes]
        if len(shapes) != len(set(shapes)):
            raise ValueError("duplicate shape in unmatched_shapes")
        keys = [(-u.count, u.shape) for u in self.unmatched_shapes]
        if keys != sorted(keys):
            raise ValueError(
                "unmatched_shapes must be ranked by count descending, "
                "then shape ascending"
            )
        return self
