from uuid import uuid4

import pytest

from vsn_lead_engine.saas.authorization import AuthorizationError, require_permission
from vsn_lead_engine.saas.contracts import Entitlement, Membership
from vsn_lead_engine.saas.usage import UsageLimitError, UsageSnapshot, enforce_usage


def test_viewer_cannot_write_jobs():
    user_id, workspace_id = uuid4(), uuid4()
    membership = Membership(workspace_id=workspace_id, user_id=user_id, role="viewer")
    with pytest.raises(AuthorizationError, match="lacks permission"):
        require_permission(
            membership, "jobs:write", user_id=user_id, workspace_id=workspace_id
        )


def test_member_can_run_jobs_but_not_manage_members():
    user_id, workspace_id = uuid4(), uuid4()
    membership = Membership(workspace_id=workspace_id, user_id=user_id, role="member")
    require_permission(
        membership, "jobs:write", user_id=user_id, workspace_id=workspace_id
    )
    with pytest.raises(AuthorizationError, match="lacks permission"):
        require_permission(
            membership, "members:write", user_id=user_id, workspace_id=workspace_id
        )


def test_permission_requires_authenticated_user_membership():
    membership = Membership(workspace_id=uuid4(), user_id=uuid4(), role="owner")
    with pytest.raises(AuthorizationError, match="authenticated user"):
        require_permission(
            membership, "workspace:write", user_id=uuid4(),
            workspace_id=membership.workspace_id,
        )


def test_permission_requires_requested_workspace_membership():
    membership = Membership(workspace_id=uuid4(), user_id=uuid4(), role="owner")
    with pytest.raises(AuthorizationError, match="requested workspace"):
        require_permission(
            membership, "workspace:write", user_id=membership.user_id,
            workspace_id=uuid4(),
        )


def test_usage_enforcement_is_incremental():
    entitlement = Entitlement(workspace_id=uuid4(), plan_code="starter", lead_limit=100, job_limit=3)
    snapshot = enforce_usage(entitlement, UsageSnapshot(), leads=40, jobs=1)
    assert snapshot == UsageSnapshot(leads_used=40, jobs_used=1)
    with pytest.raises(UsageLimitError, match="lead"):
        enforce_usage(entitlement, snapshot, leads=61)
    with pytest.raises(UsageLimitError, match="job"):
        enforce_usage(entitlement, snapshot, jobs=3)
