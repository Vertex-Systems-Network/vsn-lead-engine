"""Read-only single-job internal budget headroom estimate, never a reservation.

This consumes the same settled + pending counters as reserve_usage but cannot
lock an execution budget, attest source rights, or approve automation.
"""

from django.db.models import Q
from django.utils import timezone

from .models import UsagePeriod
from .usage import amounts
from .usage_snapshot import usage_snapshot

CAPACITY_ORDER = ("leads", "jobs", "provider_calls")


def single_job_budget_snapshot(actor, workspace_id, *, result_limit, provider_calls):
    requested = amounts({"leads": result_limit, "jobs": 1, "provider_calls": provider_calls})
    snapshot = usage_snapshot(actor, workspace_id)
    period = snapshot["period"]
    current_window = True
    if period is not None:
        current_window = UsagePeriod.objects.filter(
            Q(workspace_id=workspace_id),
            Q(pk=period["id"]),
            Q(status="open"),
            Q(starts_at__lte=timezone.now()),
            Q(ends_at__gt=timezone.now()),
        ).exists()
    capacity = []
    for name in CAPACITY_ORDER:
        counter = snapshot["counters"][name]
        available = max(0, counter["limit"] - counter["settled"] - counter["reserved"])
        capacity.append(
            {
                "name": name,
                "requested": requested[name],
                "settled": counter["settled"],
                "reserved": counter["reserved"],
                "limit": counter["limit"],
                "headroom": available,
            }
        )
    if not snapshot["entitlement_active"]:
        status = "entitlement_unavailable"
    elif not current_window:
        status = "accounting_window_unavailable"
    elif all(row["requested"] <= row["headroom"] for row in capacity):
        status = "advisory_single_job_fits"
    else:
        status = "advisory_single_job_exceeds"
    return {
        "status": status,
        "single_job_only": True,
        "advisory_only": True,
        "accounting": snapshot["accounting"],
        "counters": capacity,
    }


def unavailable_budget_snapshot():
    return {
        "status": "unavailable",
        "single_job_only": True,
        "advisory_only": True,
        "accounting": "unavailable",
        "counters": [],
    }
