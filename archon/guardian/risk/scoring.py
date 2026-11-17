from archon.guardian.models import SecurityFinding

_SEVERITY_WEIGHT = {
    "critical": 100,
    "high": 75,
    "medium": 40,
    "low": 15,
    "info": 0,
}


def calculate_risk_score(findings: list[SecurityFinding]) -> int:
    """Return a bounded score; a critical finding always produces 100."""
    if not findings:
        return 0

    return min(
        100,
        sum(_SEVERITY_WEIGHT[item.severity] for item in findings),
    )