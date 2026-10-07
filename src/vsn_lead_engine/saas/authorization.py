from __future__ import annotations

from .contracts import Membership


class AuthorizationError(PermissionError):
    """Raised when a workspace action is not allowed for a membership."""


ROLE_PERMISSIONS = {
    "owner": frozenset({"workspace:read", "workspace:write", "members:write", "jobs:write", "leads:read", "leads:export"}),
    "admin": frozenset({"workspace:read", "workspace:write", "members:write", "jobs:write", "leads:read", "leads:export"}),
    "member": frozenset({"workspace:read", "jobs:write", "leads:read", "leads:export"}),
    "viewer": frozenset({"workspace:read", "leads:read"}),
}


def require_permission(membership: Membership, permission: str) -> None:
    if permission not in ROLE_PERMISSIONS[membership.role]:
        raise AuthorizationError(f"role {membership.role} lacks permission: {permission}")
