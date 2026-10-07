from __future__ import annotations

from dataclasses import dataclass

from .contracts import Entitlement


class UsageLimitError(ValueError):
    """Raised when a requested operation exceeds a workspace entitlement."""


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    leads_used: int = 0
    jobs_used: int = 0

    def __post_init__(self) -> None:
        if self.leads_used < 0 or self.jobs_used < 0:
            raise ValueError("usage counters cannot be negative")


def enforce_usage(entitlement: Entitlement, usage: UsageSnapshot, *, leads: int = 0, jobs: int = 0) -> UsageSnapshot:
    if leads < 0 or jobs < 0:
        raise UsageLimitError("requested usage cannot be negative")
    if entitlement.lead_limit is not None and usage.leads_used + leads > entitlement.lead_limit:
        raise UsageLimitError("lead entitlement exceeded")
    if entitlement.job_limit is not None and usage.jobs_used + jobs > entitlement.job_limit:
        raise UsageLimitError("job entitlement exceeded")
    return UsageSnapshot(usage.leads_used + leads, usage.jobs_used + jobs)
