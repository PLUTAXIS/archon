from archon.guardian.models import Action, PolicyDecision, SecurityFinding
from archon.guardian.policy.defaults import RULE_ACTION, SEVERITY_ACTION
from archon.guardian.security.engine import normalize_findings

_ACTION_PRIORITY = {
    "allow": 0,
    "warn": 1,
    "approval_required": 2,
    "block": 3,
}


def _action_for(finding: SecurityFinding) -> Action:
    """Critical findings always block, regardless of rule overrides."""
    if finding.severity == "critical":
        return "block"

    return RULE_ACTION.get(
        finding.rule_id,
        SEVERITY_ACTION[finding.severity],
    )


class PolicyEngine:
    """Evaluate findings using deterministic, explicit policy rules."""

    def evaluate(
        self,
        findings: list[SecurityFinding],
    ) -> PolicyDecision:
        ordered = normalize_findings(findings)

        if not ordered:
            return PolicyDecision(
                action="allow",
                reasons=["No security findings were supplied."],
                finding_ids=[],
            )

        decisions = [
            (_action_for(finding), finding)
            for finding in ordered
        ]

        strongest = max(
            (action for action, _ in decisions),
            key=lambda action: _ACTION_PRIORITY[action],
        )

        reasons = [
            f"{finding.rule_id}: {action} ({finding.title})"
            for action, finding in decisions
            if action == strongest
        ]

        return PolicyDecision(
            action=strongest,
            reasons=reasons,
            finding_ids=[finding.finding_id for _, finding in decisions],
        )