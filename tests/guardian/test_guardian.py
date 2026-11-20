import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from archon.guardian.audit.logger import AuditLogger
from archon.guardian.authorization.engine import AuthorizationEngine
from archon.guardian.engine import GuardianEngine
from archon.guardian.models import (
    ApprovalGrant,
    AuthorizationContext,
    Operation,
    Role,
    SecurityFinding,
)


def finding(
    finding_id: str = "f-1",
    rule_id: str = "code.issue",
    severity: str = "medium",
) -> SecurityFinding:
    return SecurityFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        severity=severity,
        title="Test finding",
        evidence="Deterministic test evidence",
        source="unit-test",
    )


def test_empty_assessment_is_allowed() -> None:
    result = GuardianEngine().assess([])
    assert result.decision.action == "allow"
    assert result.risk_score == 0


def test_critical_finding_blocks_and_scores_100() -> None:
    result = GuardianEngine().assess([
        finding(rule_id="dependency.critical", severity="critical")
    ])
    assert result.decision.action == "block"
    assert result.risk_score == 100


def test_critical_finding_cannot_be_downgraded_by_rule_override() -> None:
    result = GuardianEngine().assess([
        finding(
            rule_id="workflow.write_all_permissions",
            severity="critical",
        )
    ])
    assert result.decision.action == "block"


def test_secret_rule_blocks_even_if_severity_is_low() -> None:
    result = GuardianEngine().assess([
        finding(rule_id="secret.exposed", severity="low")
    ])
    assert result.decision.action == "block"


def test_high_severity_requires_approval() -> None:
    result = GuardianEngine().assess([
        finding(severity="high")
    ])
    assert result.decision.action == "approval_required"


def test_duplicate_finding_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate finding_id"):
        GuardianEngine().assess([
            finding("duplicate"),
            finding("duplicate"),
        ])


def test_finding_order_is_deterministic() -> None:
    result = GuardianEngine().assess([
        finding("z", severity="low"),
        finding("a", severity="critical"),
    ])
    assert [item.finding_id for item in result.findings] == ["a", "z"]



def trusted_role(actor: str) -> Role | None:
    roles: dict[str, Role] = {
        "reviewer": "viewer",
        "analyst": "analyst",
        "admin": "admin",
    }
    return roles.get(actor)


def valid_grant(
    actor: str = "admin",
    approved_by: str = "reviewer",
    operation: Operation = "merge",
    resource: str = "repo:main",
    expires_at: datetime | None = None,
) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id="approval-001",
        requested_actor=actor,
        approved_by=approved_by,
        operation=operation,
        resource=resource,
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=10),
        signature="test-signature",
    )


def test_authorization_denies_without_trusted_identity_provider() -> None:
    context = AuthorizationContext(
        actor="analyst",
        operation="read",
        resource="repo:main",
    )
    result = AuthorizationEngine().authorize(context)
    assert not result.allowed
    assert "identity resolver" in result.reason


def test_viewer_cannot_create_issue() -> None:
    context = AuthorizationContext(
        actor="reviewer",
        operation="create_issue",
        resource="repo:main",
    )
    result = AuthorizationEngine(role_resolver=trusted_role).authorize(context)
    assert not result.allowed


def test_analyst_can_open_pr() -> None:
    context = AuthorizationContext(
        actor="analyst",
        operation="open_pr",
        resource="repo:main",
    )
    assert AuthorizationEngine(role_resolver=trusted_role).authorize(context).allowed


def test_admin_cannot_merge_without_approval() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
    )
    result = AuthorizationEngine(role_resolver=trusted_role).authorize(context)
    assert not result.allowed
    assert "approval" in result.reason


def test_admin_can_merge_with_verified_approval() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=lambda grant, ctx: True,
    )
    assert engine.authorize(context).allowed


def test_forged_approval_is_rejected() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=lambda grant, ctx: False,
    )
    result = engine.authorize(context)
    assert not result.allowed
    assert "independently verified" in result.reason


def test_approval_for_wrong_resource_is_rejected() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:production",
        approval=valid_grant(resource="repo:staging"),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=lambda grant, ctx: True,
    )
    assert not engine.authorize(context).allowed


def test_self_approval_is_rejected() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(approved_by="admin"),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=lambda grant, ctx: True,
    )
    assert not engine.authorize(context).allowed


def test_expired_approval_is_rejected() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        ),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=lambda grant, ctx: True,
    )
    assert not engine.authorize(context).allowed


def test_approval_is_rejected_without_verifier() -> None:
    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(),
    )
    engine = AuthorizationEngine(role_resolver=trusted_role)
    assert not engine.authorize(context).allowed


def test_identity_resolver_failure_denies_access() -> None:
    def failing_resolver(actor: str) -> None:
        raise RuntimeError("identity service unavailable")

    context = AuthorizationContext(
        actor="admin",
        operation="read",
        resource="repo:main",
    )
    result = AuthorizationEngine(role_resolver=failing_resolver).authorize(context)
    assert not result.allowed


def test_approval_verifier_failure_denies_access() -> None:
    def failing_verifier(grant: ApprovalGrant, context: AuthorizationContext) -> bool:
        raise RuntimeError("approval service unavailable")

    context = AuthorizationContext(
        actor="admin",
        operation="merge",
        resource="repo:main",
        approval=valid_grant(),
    )
    engine = AuthorizationEngine(
        role_resolver=trusted_role,
        approval_verifier=failing_verifier,
    )
    assert not engine.authorize(context).allowed


def test_audit_chain_detects_tampering(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    logger = AuditLogger(path)

    logger.append("analyst", "investigate", "completed")
    logger.append("admin", "approve", "approved")

    assert logger.verify()

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT event_json FROM audit_events WHERE sequence = 1"
        ).fetchone()
        assert row is not None

        payload = json.loads(row[0])
        payload["action"] = "tampered"

        connection.execute(
            "UPDATE audit_events SET event_json = ? WHERE sequence = 1",
            (json.dumps(payload, sort_keys=True),),
        )

    assert not logger.verify()

def test_audit_chain_links_events(tmp_path) -> None:
    logger = AuditLogger(tmp_path / "audit.sqlite3")
    first = logger.append("analyst", "scan", "completed")
    second = logger.append("admin", "review", "approved")

    assert second.sequence == first.sequence + 1
    assert second.previous_hash == first.event_hash
    assert logger.verify()


def test_audit_concurrent_appends_are_serialized(tmp_path) -> None:
    logger = AuditLogger(tmp_path / "audit.sqlite3")

    def append_event(index: int) -> int:
        event = logger.append(
            "analyst",
            "investigate",
            "completed",
            details={"index": str(index)},
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(append_event, range(40)))

    assert sorted(sequences) == list(range(1, 41))
    assert logger.verify()

def test_audit_verification_fails_closed_on_malformed_event(
    tmp_path,
) -> None:
    path = tmp_path / "audit.sqlite3"
    logger = AuditLogger(path)

    logger.append("analyst", "investigate", "completed")

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE audit_events
            SET event_json = ?
            WHERE sequence = 1
            """,
            ("not-valid-json",),
        )

    assert not logger.verify()