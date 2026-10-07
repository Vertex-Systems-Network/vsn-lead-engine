from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import FrozenSet, Mapping, Optional
from uuid import UUID, uuid4


class JobStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Workspace:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    timezone: str = "UTC"
    owner_user_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("workspace name is required")
        if not self.timezone.strip():
            raise ValueError("workspace timezone is required")


@dataclass(frozen=True, slots=True)
class Membership:
    workspace_id: UUID
    user_id: UUID
    role: str = "member"

    VALID_ROLES: FrozenSet[str] = frozenset({"owner", "admin", "member", "viewer"})

    def __post_init__(self) -> None:
        if self.role not in self.VALID_ROLES:
            raise ValueError(f"unsupported workspace role: {self.role}")


@dataclass(frozen=True, slots=True)
class Entitlement:
    workspace_id: UUID
    plan_code: str
    active: bool = True
    lead_limit: int | None = None
    job_limit: int | None = None
    export_enabled: bool = True
    source_codes: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.plan_code.strip():
            raise ValueError("plan code is required")
        for name, value in (("lead_limit", self.lead_limit), ("job_limit", self.job_limit)):
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class SearchSpec:
    workspace_id: UUID
    countries: tuple[str, ...]
    categories: tuple[str, ...]
    statuses: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    source_codes: tuple[str, ...] = ()
    result_limit: int = 100

    def __post_init__(self) -> None:
        if not self.countries:
            raise ValueError("at least one country is required")
        if not self.categories:
            raise ValueError("at least one category is required")
        if self.result_limit <= 0:
            raise ValueError("result limit must be positive")
        if any(not value.strip() for value in (*self.countries, *self.categories, *self.source_codes)):
            raise ValueError("search values cannot be blank")


@dataclass(slots=True)
class Job:
    workspace_id: UUID
    search: SearchSpec
    id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None
    result_count: int = 0
    metadata: Mapping[str, str] = field(default_factory=dict)

    def transition(self, status: JobStatus, *, error: str | None = None) -> None:
        allowed = {
            JobStatus.DRAFT: {JobStatus.QUEUED, JobStatus.CANCELLED},
            JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED},
            JobStatus.RUNNING: {JobStatus.PARTIAL, JobStatus.COMPLETED, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
            JobStatus.PARTIAL: {JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
            JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
            JobStatus.COMPLETED: set(),
            JobStatus.FAILED: {JobStatus.QUEUED},
            JobStatus.CANCELLED: set(),
        }
        if status not in allowed[self.status]:
            raise ValueError(f"invalid job transition: {self.status.value} -> {status.value}")
        self.status = status
        self.error = error
        self.updated_at = datetime.now(timezone.utc)
