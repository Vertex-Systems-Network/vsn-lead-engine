from uuid import uuid4

import pytest

from vsn_lead_engine.saas import Entitlement, Job, JobStatus, Membership, SearchSpec, Workspace


def test_workspace_membership_and_entitlement_are_tenant_scoped():
    workspace = Workspace(name="Acme", timezone="Asia/Karachi")
    membership = Membership(workspace_id=workspace.id, user_id=uuid4(), role="admin")
    entitlement = Entitlement(workspace_id=workspace.id, plan_code="free", lead_limit=100)

    assert membership.workspace_id == workspace.id
    assert entitlement.workspace_id == workspace.id


def test_search_requires_scope_and_positive_limit():
    workspace_id = uuid4()
    with pytest.raises(ValueError):
        SearchSpec(workspace_id=workspace_id, countries=(), categories=("spa",))
    with pytest.raises(ValueError):
        SearchSpec(workspace_id=workspace_id, countries=("US",), categories=("spa",), result_limit=0)


def test_job_lifecycle_rejects_invalid_transition():
    spec = SearchSpec(workspace_id=uuid4(), countries=("US",), categories=("spa",))
    job = Job(workspace_id=spec.workspace_id, search=spec)
    job.transition(JobStatus.QUEUED)
    job.transition(JobStatus.RUNNING)
    job.transition(JobStatus.COMPLETED)

    with pytest.raises(ValueError):
        job.transition(JobStatus.RUNNING)
