"""Contract F (report section tree): structural rules."""

import pytest
from pydantic import ValidationError

from archon.contracts.report import ReportDocument

WB = "5b0f1c1e-8f4e-4c55-9d0e-3c1b2a7d9e11"


def _entry(status: str = "matched", text: str | None = "Sum.") -> dict:
    return {
        "node_id": "Revenue!R1C7#c17",
        "status": status,
        "plain_english": text,
        "risk_score": 0,
        "risk_flags": [],
    }


def _section(
    sid: str, kind: str, entries: list[dict], children: list[dict] | None = None
) -> dict:
    return {
        "section_id": sid,
        "kind": kind,
        "title": sid,
        "entries": entries,
        "children": children or [],
    }


def _doc(sections: list[dict]) -> dict:
    return {"schema_version": "1.0", "workbook_id": WB, "sections": sections}


def _appendix(entries: list[dict] | None = None) -> dict:
    return _section("appendix", "unverified_appendix", entries or [])


def test_valid_document() -> None:
    doc = ReportDocument.model_validate(
        _doc([_section("s1", "explanations", [_entry()]), _appendix()])
    )
    assert doc.sections[0].section_id == "s1"


def test_appendix_is_required() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc([_section("s1", "explanations", [_entry()])])
        )


def test_appendix_exactly_once() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc([_appendix(), _section("a2", "unverified_appendix", [])])
        )


def test_appendix_only_unverified() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(_doc([_appendix([_entry()])]))


def test_duplicate_section_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc(
                [
                    _section("s1", "explanations", []),
                    _section("s1", "risk", []),
                    _appendix(),
                ]
            )
        )


def test_matched_entry_needs_text() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc([_section("s1", "explanations", [_entry(text=None)]), _appendix()])
        )


def test_unverified_entry_has_no_text() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc(
                [
                    _section("s1", "explanations", [_entry("unverified", "x")]),
                    _appendix(),
                ]
            )
        )


def test_extra_field_forbidden() -> None:
    data = _doc([_appendix()])
    data["oops"] = 1
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(data)


def test_sections_has_no_default() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate({"schema_version": "1.0", "workbook_id": WB})


def test_nested_duplicate_section_id_rejected() -> None:
    child = _section("s1", "risk", [])
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc([_section("s1", "explanations", [], [child]), _appendix()])
        )


def test_nested_duplicate_of_other_top_level_rejected() -> None:
    child = _section("s2", "risk", [])
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc(
                [
                    _section("s1", "explanations", [], [child]),
                    _section("s2", "bugs", []),
                    _appendix(),
                ]
            )
        )


def test_non_v4_workbook_id_accepted() -> None:
    data = _doc([_appendix()])
    data["workbook_id"] = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ReportDocument.model_validate(data)


def test_matched_entry_whitespace_text_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportDocument.model_validate(
            _doc([_section("s1", "explanations", [_entry(text="   ")]), _appendix()])
        )
