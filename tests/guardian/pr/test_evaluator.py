import pytest
from pydantic import ValidationError

from archon.guardian.models import SecurityFinding
from archon.guardian.pr.evaluator import PREvaluator
from archon.guardian.pr.models import (
    PRCheck,
    PRReview,
    PullRequestEvidence,
)


def make_pr(**overrides) -> PullRequestEvidence:
    values = {
        "repository": "example/project",
        "number": 12,
        "base_branch": "main",
        "head_sha": "abc123",
        "actor": "contributor",
        "findings": [],
        "checks": [
            PRCheck(name="tests", status="passed"),
            PRCheck(name="lint", status="passed"),
        ],
        "required_check_names": ["tests", "lint"],
        "reviews": [
            PRReview(reviewer="maintainer", state="approved"),
        ],
        "required_approvals": 1,
        "merge_authorized": True,
    }
    values.update(overrides)
    return PullRequestEvidence(**values)


def finding(
    finding_id: str = "F-1",
    rule_id: str = "test.rule",
    severity: str = "low",
) -> SecurityFinding:
    return SecurityFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        severity=severity,
        title="Test finding",
        evidence="Synthetic test evidence",
        source="unit-test",
    )


def test_clean_pr_is_eligible_for_auto_merge():
    result = PREvaluator().evaluate(make_pr())

    assert result.decision == "AUTO_MERGE"
    assert result.risk_score == 0


def test_critical_finding_blocks_pr():
    result = PREvaluator().evaluate(
        make_pr(findings=[finding(severity="critical")])
    )

    assert result.decision == "BLOCK"
    assert result.risk_score == 100


def test_exposed_secret_blocks_even_with_low_severity():
    result = PREvaluator().evaluate(
        make_pr(
            findings=[
                finding(rule_id="secret.exposed", severity="low")
            ]
        )
    )

    assert result.decision == "BLOCK"


def test_high_severity_requires_approval():
    result = PREvaluator().evaluate(
        make_pr(findings=[finding(severity="high")])
    )

    assert result.decision == "REQUIRE_APPROVAL"


def test_failed_required_check_blocks():
    result = PREvaluator().evaluate(
        make_pr(
            checks=[
                PRCheck(name="tests", status="failed"),
                PRCheck(name="lint", status="passed"),
            ]
        )
    )

    assert result.decision == "BLOCK"


def test_pending_required_check_does_not_auto_merge():
    result = PREvaluator().evaluate(
        make_pr(
            checks=[
                PRCheck(name="tests", status="pending"),
                PRCheck(name="lint", status="passed"),
            ]
        )
    )

    assert result.decision == "REQUIRE_APPROVAL"


def test_missing_required_check_evidence_is_rejected():
    with pytest.raises(ValidationError):
        make_pr(
            checks=[PRCheck(name="tests", status="passed")]
        )


def test_missing_human_approval_requires_approval():
    result = PREvaluator().evaluate(
        make_pr(reviews=[], required_approvals=1)
    )

    assert result.decision == "REQUIRE_APPROVAL"


def test_missing_merge_authorization_requires_approval():
    result = PREvaluator().evaluate(
        make_pr(merge_authorized=False)
    )

    assert result.decision == "REQUIRE_APPROVAL"


def test_changes_requested_blocks():
    result = PREvaluator().evaluate(
        make_pr(
            reviews=[
                PRReview(
                    reviewer="maintainer",
                    state="changes_requested",
                )
            ]
        )
    )

    assert result.decision == "BLOCK"


def test_duplicate_reviewers_are_rejected():
    with pytest.raises(ValidationError):
        make_pr(
            reviews=[
                PRReview(reviewer="maintainer", state="approved"),
                PRReview(reviewer="maintainer", state="approved"),
            ]
        )


def test_duplicate_check_names_are_rejected():
    with pytest.raises(ValidationError):
        make_pr(
            checks=[
                PRCheck(name="tests", status="passed"),
                PRCheck(name="tests", status="passed"),
            ]
        )
