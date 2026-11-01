import re
from typing import Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator


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