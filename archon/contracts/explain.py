from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

IdiomType = Literal[
    "tiered_rate_table",
    "running_balance",
    "product",
    "sum",
    "difference",
    "ratio",
    "rounding",
    "lookup",
    "error_suppression",
    "volatile_function",
    "other",
]


class Evidence(BaseModel):
    model_config = {"extra": "forbid"}
    pattern_id: str | None = None
    captured_vars: dict[str, str] = Field(default_factory=dict)
    header_resolved: bool
    header_terms: list[str] = Field(default_factory=list)


class ExplanationRecord(BaseModel):
    model_config = {"extra": "forbid"}
    node_id: str
    status: Literal["matched", "unverified"]
    idiom: IdiomType | None = None
    plain_english: str | None = None
    business_concept: str | None = None
    evidence: Evidence | None = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    @model_validator(mode="after")
    def status_must_match_populated_fields(self) -> Self:
        """Enforce that 'unverified' records carry no invented explanation, and
        'matched' records always carry an idiom. This stops a bug from accidentally
        producing a fabricated explanation for a formula the engine did not recognize."""
        if self.status == "unverified" and (
            self.idiom is not None
            or self.business_concept is not None
            or self.evidence is not None
        ):
            raise ValueError(
                "unverified records must have idiom, business_concept, "
                "and evidence set to None"
            )
        if self.status == "matched" and self.idiom is None:
            raise ValueError("matched records must have an idiom set")
        if self.status == "matched" and not (self.plain_english or "").strip():
            raise ValueError("matched records must have non-empty plain_english")
        return self
