from __future__ import annotations

from uuid import UUID

from .contracts import Membership


class AuthorizationError(PermissionError):
    """Raised when a workspace action is not allowed for a membership."""


ROLE_PERMISSIONS = {
    "owner": frozenset({"workspace:read", "workspace:write", "members:write", "jobs:write", "leads:read", "leads:export"}),
    "admin": frozenset({"workspace:read", "workspace:write", "members:write", "jobs:write", "leads:read", "leads:export"}),
    "member": frozenset({"workspace:read", "jobs:write", "leads:read", "leads:export"}),
    "viewer": frozenset({"workspace:read", "leads:read"}),
}


def require_membership(membership: Membership, *, user_id: UUID, workspace_id: UUID) -> None:
    """Bind an authorization decision to both the authenticated actor and tenant."""
    if membership.user_id != user_id:
        raise AuthorizationError("membership does not belong to authenticated user")
    if membership.workspace_id != workspace_id:
        raise AuthorizationError("membership does not belong to requested workspace")


def require_permission(
    membership: Membership,
    permission: str,
    *,
    user_id: UUID,
    workspace_id: UUID,
) -> None:
    require_membership(membership, user_id=user_id, workspace_id=workspace_id)
    if permission not in ROLE_PERMISSIONS[membership.role]:
        raise AuthorizationError(f"role {membership.role} lacks permission: {permission}")
