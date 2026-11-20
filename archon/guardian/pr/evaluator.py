from archon.guardian.engine import GuardianEngine
from archon.guardian.pr.models import MergeEvaluation, PullRequestEvidence


class PREvaluator:
    def __init__(self, guardian: GuardianEngine | None = None) -> None:
        self.guardian = guardian or GuardianEngine()

    def evaluate(self, evidence: PullRequestEvidence) -> MergeEvaluation:
        assessment = self.guardian.assess(evidence.findings)
        reasons: list[str] = []

        if assessment.decision.action == "block":
            reasons.extend(assessment.decision.reasons)
            decision = "BLOCK"

        else:
            check_statuses = {
                check.name: check.status for check in evidence.checks
            }
            required_statuses = [
                check_statuses[name]
                for name in evidence.required_check_names
            ]

            if any(status in {"failed", "missing"} for status in required_statuses):
                reasons.append("A required CI check failed or is missing.")
                decision = "BLOCK"

            elif any(status == "pending" for status in required_statuses):
                reasons.append("Required CI checks are still pending.")
                decision = "REQUIRE_APPROVAL"

            elif any(
                review.state == "changes_requested"
                for review in evidence.reviews
            ):
                reasons.append("A reviewer requested changes.")
                decision = "BLOCK"

            else:
                approved_reviewers = {
                    review.reviewer.casefold()
                    for review in evidence.reviews
                    if review.state == "approved"
                    and review.reviewer.casefold() != evidence.actor.casefold()
                }

                if assessment.decision.action in {"warn", "approval_required"}:
                    reasons.extend(assessment.decision.reasons)
                    decision = "REQUIRE_APPROVAL"

                elif len(approved_reviewers) < evidence.required_approvals:
                    reasons.append("Required independent human approvals are missing.")
                    decision = "REQUIRE_APPROVAL"

                elif not evidence.merge_authorized:
                    reasons.append("A trusted merge authorization is missing.")
                    decision = "REQUIRE_APPROVAL"

                else:
                    reasons.append(
                        "Policy, required checks, reviews, and authorization "
                        "permit merging."
                    )
                    decision = "AUTO_MERGE"

        return MergeEvaluation(
            decision=decision,
            reasons=reasons,
            risk_score=assessment.risk_score,
            repository=evidence.repository,
            pull_request=evidence.number,
            head_sha=evidence.head_sha,
        )
