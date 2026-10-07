from uuid import uuid4

import pytest

from vsn_lead_engine.saas.authorization import AuthorizationError, require_permission
from vsn_lead_engine.saas.contracts import Entitlement, Membership
from vsn_lead_engine.saas.usage import UsageLimitError, UsageSnapshot, enforce_usage


def test_viewer_cannot_write_jobs():
    membership = Membership(workspace_id=uuid4(), user_id=uuid4(), role="viewer")
    with pytest.raises(AuthorizationError, match="lacks permission"):
        require_permission(membership, "jobs:write")


def test_member_can_run_jobs_but_not_manage_members():
    membership = Membership(workspace_id=uuid4(), user_id=uuid4(), role="member")
    require_permission(membership, "jobs:write")
    with pytest.raises(AuthorizationError):
        require_permission(membership, "members:write")


def test_usage_enforcement_is_incremental():
    entitlement = Entitlement(workspace_id=uuid4(), plan_code="starter", lead_limit=100, job_limit=3)
    snapshot = enforce_usage(entitlement, UsageSnapshot(), leads=40, jobs=1)
    assert snapshot == UsageSnapshot(leads_used=40, jobs_used=1)
    with pytest.raises(UsageLimitError, match="lead"):
        enforce_usage(entitlement, snapshot, leads=61)
    with pytest.raises(UsageLimitError, match="job"):
        enforce_usage(entitlement, snapshot, jobs=3)
