from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from uuid import UUID

from .authorization import require_permission
from .contracts import Job, Membership, Workspace


class DuplicateIdempotencyKey(ValueError):
    """Raised when a key is reused with a different operation payload."""


class TenantNotFound(LookupError):
    """Raised when a resource is not visible in the requested workspace."""


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    operation: str
    request_hash: str
    result_id: UUID


class InMemorySaaSRepository:
    """Deterministic tenant-scoped repository for API/service tests.

    This is intentionally not production persistence. It provides a safe,
    dependency-free seam until the selected Django/PostgreSQL runtime lands.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._workspaces: dict[UUID, Workspace] = {}
        self._memberships: dict[tuple[UUID, UUID], Membership] = {}
        self._jobs: dict[UUID, Job] = {}
        self._idempotency: dict[tuple[UUID, str], IdempotencyRecord] = {}

    def add_workspace(self, workspace: Workspace) -> Workspace:
        with self._lock:
            self._workspaces[workspace.id] = workspace
        return workspace

    def add_membership(self, membership: Membership) -> Membership:
        with self._lock:
            if membership.workspace_id not in self._workspaces:
                raise TenantNotFound("workspace does not exist")
            self._memberships[(membership.workspace_id, membership.user_id)] = membership
        return membership

    def require_membership(self, *, user_id: UUID, workspace_id: UUID) -> Membership:
        with self._lock:
            membership = self._memberships.get((workspace_id, user_id))
            if membership is None:
                raise TenantNotFound("workspace resource not found")
            return membership

    def save_job(self, job: Job, *, user_id: UUID, idempotency_key: str,
                 request_hash: str) -> Job:
        if not idempotency_key.strip() or not request_hash.strip():
            raise ValueError("idempotency key and request hash are required")
        with self._lock:
            membership = self.require_membership(user_id=user_id, workspace_id=job.workspace_id)
            require_permission(membership, "jobs:write", user_id=user_id, workspace_id=job.workspace_id)
            key = (job.workspace_id, idempotency_key)
            previous = self._idempotency.get(key)
            if previous is not None:
                if previous.operation != "job.create" or previous.request_hash != request_hash:
                    raise DuplicateIdempotencyKey("idempotency key payload conflict")
                return deepcopy(self._jobs[previous.result_id])
            if job.id in self._jobs:
                raise ValueError("job ID already exists")
            self._jobs[job.id] = deepcopy(job)
            self._idempotency[key] = IdempotencyRecord(
                "job.create", request_hash, job.id
            )
            return deepcopy(job)

    def get_job(self, *, job_id: UUID, user_id: UUID, workspace_id: UUID) -> Job:
        with self._lock:
            membership = self.require_membership(user_id=user_id, workspace_id=workspace_id)
            require_permission(membership, "workspace:read", user_id=user_id, workspace_id=workspace_id)
            job = self._jobs.get(job_id)
            if job is None or job.workspace_id != workspace_id:
                raise TenantNotFound("workspace resource not found")
            return deepcopy(job)
