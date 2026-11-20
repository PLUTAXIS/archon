from archon.guardian.models import SecurityFinding

_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def normalize_findings(
    findings: list[SecurityFinding],
) -> list[SecurityFinding]:
    """Validate uniqueness and return findings in deterministic order."""
    ids = [finding.finding_id for finding in findings]

    if len(ids) != len(set(ids)):
        raise ValueError("duplicate finding_id")

    return sorted(
        findings,
        key=lambda item: (
            _SEVERITY_ORDER[item.severity],
            item.rule_id,
            item.finding_id,
        ),
    )