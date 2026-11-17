from archon.guardian.models import GuardianAssessment, SecurityFinding
from archon.guardian.policy.engine import PolicyEngine
from archon.guardian.risk.scoring import calculate_risk_score
from archon.guardian.security.engine import normalize_findings


class GuardianEngine:
    """Coordinate deterministic security, policy, and risk evaluation."""

    def __init__(self) -> None:
        self.policy = PolicyEngine()

    def assess(
        self,
        findings: list[SecurityFinding],
    ) -> GuardianAssessment:
        normalized = normalize_findings(findings)

        return GuardianAssessment(
            findings=normalized,
            decision=self.policy.evaluate(normalized),
            risk_score=calculate_risk_score(normalized),
        )