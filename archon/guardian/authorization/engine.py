from collections.abc import Callable
from datetime import UTC, datetime

from archon.guardian.models import (
    ApprovalGrant,
    AuthorizationContext,
    AuthorizationResult,
    Role,
)

RoleResolver = Callable[[str], Role | None]
ApprovalVerifier = Callable[[ApprovalGrant, AuthorizationContext], bool]

_ROLE_OPERATIONS = {
    "viewer": {"read"},
    "analyst": {
        "read",
        "comment",
        "create_issue",
        "create_branch",
        "open_pr",
    },
    "admin": {
        "read",
        "comment",
        "create_issue",
        "create_branch",
        "open_pr",
        "modify_workflow",
        "merge",
        "deploy",
    },
}

_APPROVAL_REQUIRED = {
    "modify_workflow",
    "merge",
    "deploy",
}


class AuthorizationEngine:
    """Authorize operations using trusted identity and approval providers.

    The role resolver must use an authenticated identity source.
    The approval verifier must validate the grant signature and approver
    permissions against a trusted source. Neither provider should trust
    caller-supplied claims without independent verification.
    """

    def __init__(
        self,
        role_resolver: RoleResolver | None = None,
        approval_verifier: ApprovalVerifier | None = None,
    ) -> None:
        self.role_resolver = role_resolver
        self.approval_verifier = approval_verifier

    def authorize(
        self,
        context: AuthorizationContext,
    ) -> AuthorizationResult:
        if self.role_resolver is None:
            return AuthorizationResult(
                allowed=False,
                reason="No trusted identity resolver is configured.",
            )

        try:
            role = self.role_resolver(context.actor)
        except Exception:  # noqa: BLE001
            role = None

        if role not in _ROLE_OPERATIONS:
            return AuthorizationResult(
                allowed=False,
                reason="The actor could not be authenticated or resolved.",
            )

        if context.operation not in _ROLE_OPERATIONS[role]:
            return AuthorizationResult(
                allowed=False,
                reason="The actor's verified role does not permit this operation.",
            )

        if context.operation not in _APPROVAL_REQUIRED:
            return AuthorizationResult(
                allowed=True,
                reason="The operation is permitted by the verified role policy.",
            )

        grant = context.approval

        if grant is None:
            return AuthorizationResult(
                allowed=False,
                reason="A trusted human approval is required.",
            )

        if (
            grant.requested_actor != context.actor
            or grant.operation != context.operation
            or grant.resource != context.resource
        ):
            return AuthorizationResult(
                allowed=False,
                reason="The approval does not match this actor, operation, and resource.",
            )

        if grant.approved_by == context.actor:
            return AuthorizationResult(
                allowed=False,
                reason="The requester cannot approve their own operation.",
            )

        if (
            grant.expires_at.tzinfo is None
            or grant.expires_at.utcoffset() is None
            or grant.expires_at <= datetime.now(UTC)
        ):
            return AuthorizationResult(
                allowed=False,
                reason="The approval is expired or has an invalid timestamp.",
            )

        if self.approval_verifier is None:
            return AuthorizationResult(
                allowed=False,
                reason="No trusted approval verifier is configured.",
            )

        try:
            verified = self.approval_verifier(grant, context)
        except Exception:  # noqa: BLE001
            verified = False

        if not verified:
            return AuthorizationResult(
                allowed=False,
                reason="The approval could not be independently verified.",
            )

        return AuthorizationResult(
            allowed=True,
            reason="The operation and its scoped approval were verified.",
        )
