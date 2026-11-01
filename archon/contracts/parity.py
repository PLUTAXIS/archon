import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class TolerancePolicy(BaseModel):
    model_config = {"extra": "forbid"}
    float_relative: float
    date_mode: str
    rounding: str
    empty_cell: str


class CaseResult(BaseModel):
    model_config = {"extra": "forbid"}
    case_id: int
    inputs: dict[str, Any]
    excel: float | str | bool | None
    python: float | str | bool | None
    delta: float


class Signature(BaseModel):
    model_config = {"extra": "forbid"}
    alg: str
    pubkey: str
    sig: str


class ParityCertificate(BaseModel):
    model_config = {"extra": "forbid"}
    certificate_id: UUID
    workbook_id: UUID
    generated_at: datetime
    harness_version: str
    cases_total: int
    cases_passed: int
    match_rate: str
    tolerance_policy: TolerancePolicy
    case_results: list[CaseResult]
    signature: Signature

    @field_validator("match_rate")
    @classmethod
    def must_be_two_decimal_percentage(cls, v: str) -> str:
        """Validate match_rate is formatted exactly as a 2-decimal percentage string."""
        if not re.fullmatch(r"\d{1,3}\.\d{2}", v):
            raise ValueError("match_rate must be a 2-decimal string (e.g. '100.00')")
        return v

    @model_validator(mode="after")
    def match_rate_must_agree_with_case_counts(self) -> Self:
        """Reject a certificate where cases_passed is out of bounds for cases_total,
        or where match_rate does not equal the percentage those counts imply.
        Policy: cases_total == 0 is invalid — a certificate must cover at least
        one case, since a zero-case 'pass rate' is not a meaningful claim."""
        if self.cases_total == 0:
            raise ValueError("cases_total must be greater than 0")
        if not (0 <= self.cases_passed <= self.cases_total):
            raise ValueError("cases_passed must be between 0 and cases_total")

        expected = Decimal(self.cases_passed) * 100 / Decimal(self.cases_total)
        expected_str = f"{expected:.2f}"
        if self.match_rate != expected_str:
            raise ValueError(
                f"match_rate '{self.match_rate}' does not match the computed "
                f"rate '{expected_str}' from cases_passed/cases_total"
            )
        return self
