from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
Action = Literal["allow", "warn", "block", "approval_required"]
Role = Literal["viewer", "analyst", "admin"]
Operation = Literal[
    "read",
    "comment",
    "create_issue",
    "create_branch",
    "open_pr",
    "modify_workflow",
    "merge",
    "deploy",
]


class SecurityFinding(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: Severity
    title: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    source: str = Field(min_length=1)


class PolicyDecision(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    action: Action
    reasons: list[str]
    finding_ids: list[str]


class ApprovalGrant(BaseModel):
    """An approval claim that must be independently verified."""

    model_config = {"extra": "forbid", "frozen": True}

    approval_id: str = Field(min_length=1)
    requested_actor: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    operation: Operation
    resource: str = Field(min_length=1)
    expires_at: datetime
    signature: str = Field(min_length=1)


class AuthorizationContext(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    actor: str = Field(min_length=1)
    operation: Operation
    resource: str = Field(min_length=1)
    approval: ApprovalGrant | None = None


class AuthorizationResult(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    allowed: bool
    reason: str


class GuardianAssessment(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    findings: list[SecurityFinding]
    decision: PolicyDecision
    risk_score: int = Field(ge=0, le=100)


class AuditEvent(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    sequence: int = Field(ge=1)
    timestamp: str
    actor: str
    action: str
    outcome: str
    details: dict[str, str]
    previous_hash: str
    event_hash: str