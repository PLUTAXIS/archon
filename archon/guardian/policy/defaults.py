from archon.guardian.models import Action, Severity

SEVERITY_ACTION: dict[Severity, Action] = {
    "critical": "block",
    "high": "approval_required",
    "medium": "warn",
    "low": "allow",
    "info": "allow",
}

RULE_ACTION: dict[str, Action] = {
    "secret.exposed": "block",
    "dependency.critical": "block",
    "scan.required_missing": "block",
    "workflow.untrusted_execution": "block",
    "workflow.write_all_permissions": "approval_required",
}