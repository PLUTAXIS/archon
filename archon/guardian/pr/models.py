from typing import Literal

from pydantic import BaseModel, Field, model_validator

from archon.guardian.models import SecurityFinding

CheckStatus = Literal["passed", "failed", "pending", "missing"]
ReviewState = Literal["approved", "changes_requested", "pending"]


class PRCheck(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    name: str = Field(min_length=1)
    status: CheckStatus
    required: bool = True


class PRReview(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    reviewer: str = Field(min_length=1)
    state: ReviewState


class PullRequestEvidence(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    repository: str = Field(min_length=1)
    number: int = Field(gt=0)
    base_branch: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    findings: list[SecurityFinding] = Field(default_factory=list)
    checks: list[PRCheck] = Field(min_length=1)
    required_check_names: list[str] = Field(min_length=1)
    reviews: list[PRReview] = Field(default_factory=list)
    required_approvals: int = Field(default=1, ge=0)
    merge_authorized: bool = False

    @model_validator(mode="after")
    def validate_unique_checks(self):
        names = [check.name for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate check names are not allowed.")

        required_names = self.required_check_names
        if len(required_names) != len(set(required_names)):
            raise ValueError("Duplicate required check names are not allowed.")

        missing = set(required_names) - set(names)
        if missing:
            raise ValueError(
                f"Required checks are absent from evidence: {sorted(missing)}"
            )

        return self

    @model_validator(mode="after")
    def validate_unique_reviewers(self):
        reviewers = [review.reviewer for review in self.reviews]
        if len(reviewers) != len(set(reviewers)):
            raise ValueError("Duplicate reviewers are not allowed.")
        return self


class MergeEvaluation(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    decision: Literal["AUTO_MERGE", "REQUIRE_APPROVAL", "BLOCK"]
    reasons: list[str]
    risk_score: int = Field(ge=0, le=100)
    repository: str
    pull_request: int
    head_sha: str
