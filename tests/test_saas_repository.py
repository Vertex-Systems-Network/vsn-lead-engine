from uuid import uuid4

import pytest

from vsn_lead_engine.saas.contracts import Job, Membership, SearchSpec, Workspace
from vsn_lead_engine.saas.repository import (
    DuplicateIdempotencyKey,
    InMemorySaaSRepository,
    TenantNotFound,
)


def make_job(workspace_id):
    return Job(workspace_id=workspace_id, search=SearchSpec(
        workspace_id=workspace_id, countries=("US",), categories=("software",)
    ))


def test_jobs_are_tenant_scoped_and_cross_tenant_reads_are_hidden():
    repo = InMemorySaaSRepository()
    owner_a, owner_b = uuid4(), uuid4()
    workspace_a = repo.add_workspace(Workspace(name="A", owner_user_id=owner_a))
    workspace_b = repo.add_workspace(Workspace(name="B", owner_user_id=owner_b))
    repo.add_membership(Membership(workspace_a.id, owner_a, "owner"))
    repo.add_membership(Membership(workspace_b.id, owner_b, "owner"))
    job = repo.save_job(make_job(workspace_a.id), user_id=owner_a,
                        idempotency_key="create-1", request_hash="hash-a")

    assert repo.get_job(job_id=job.id, user_id=owner_a,
                        workspace_id=workspace_a.id) is job
    with pytest.raises(TenantNotFound):
        repo.get_job(job_id=job.id, user_id=owner_b,
                     workspace_id=workspace_b.id)


def test_same_idempotency_request_returns_original_job():
    repo = InMemorySaaSRepository()
    user = uuid4()
    workspace = repo.add_workspace(Workspace(name="A", owner_user_id=user))
    repo.add_membership(Membership(workspace.id, user, "owner"))
    first = repo.save_job(make_job(workspace.id), user_id=user,
                          idempotency_key="create-1", request_hash="same")
    second = repo.save_job(make_job(workspace.id), user_id=user,
                           idempotency_key="create-1", request_hash="same")
    assert second.id == first.id


def test_idempotency_key_cannot_change_payload():
    repo = InMemorySaaSRepository()
    user = uuid4()
    workspace = repo.add_workspace(Workspace(name="A", owner_user_id=user))
    repo.add_membership(Membership(workspace.id, user, "owner"))
    repo.save_job(make_job(workspace.id), user_id=user,
                  idempotency_key="create-1", request_hash="one")
    with pytest.raises(DuplicateIdempotencyKey):
        repo.save_job(make_job(workspace.id), user_id=user,
                      idempotency_key="create-1", request_hash="two")
