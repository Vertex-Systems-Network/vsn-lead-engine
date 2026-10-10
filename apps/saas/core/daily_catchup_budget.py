"""Advisory seven-local-day catch-up headroom estimate, never a reservation.

Only the already-authorized daily-plan readiness route calls this pure/read-only
projection. The projection cannot enable a schedule, enqueue or contact sources.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import ScheduleOccurrence
from .schedules import resolve_daily

MAX_LOCAL_DAYS = 7
RESOURCE_ORDER = ("leads", "jobs", "provider_calls")


def unavailable_catchup(status="unavailable"):
    return {
        "status": status,
        "advisory_only": True,
        "max_local_days": MAX_LOCAL_DAYS,
        "due_job_candidates": 0,
        "skipped_day_candidates": 0,
        "affordable_due_job_candidates": None,
        "deferred_due_job_candidates": None,
        "counters": [],
    }


def catchup_budget_snapshot(plan, single_budget, *, now=None):
    """Compare *all* unrecorded due local dates with the same quota snapshot.

    Preview clock and accounting may change before any real execution; no
    entitlement, legal/source, lease or delivery guarantees follow from this.
    """
    if not plan.enabled:
        return unavailable_catchup("disabled")
    if single_budget["status"] == "unavailable":
        return unavailable_catchup()

    instant = now if now is not None else timezone.now()
    zone = ZoneInfo(plan.timezone)
    local_today = instant.astimezone(zone).date()
    start = local_today - timedelta(days=MAX_LOCAL_DAYS - 1)
    existing = set(
        ScheduleOccurrence.objects.filter(
            workspace_id=plan.workspace_id,
            schedule_id=plan.pk,
            local_date__gte=start,
            local_date__lte=local_today,
        ).values_list("local_date", flat=True)
    )
    due_jobs = 0
    skipped_days = 0
    for days_back in range(MAX_LOCAL_DAYS - 1, -1, -1):
        local_date = local_today - timedelta(days=days_back)
        if local_date in existing:
            continue
        scheduled_for, _, resolution = resolve_daily(plan.timezone, local_date, plan.local_time)
        if scheduled_for is None:
            skipped_days += 1
        elif scheduled_for <= instant:
            due_jobs += 1

    capacity = [
        {**row, "requested": row["requested"] * due_jobs} for row in single_budget["counters"]
    ]
    # Simultaneous hypothetical resource intersection, NOT an ordered
    # selection or guaranteed execution. Zero-cost dimensions do not constrain.
    # An invalid entitlement/window cannot imply available job capacity.
    affordable = None
    deferred = None
    if single_budget["status"] in (
        "advisory_single_job_fits",
        "advisory_single_job_exceeds",
    ):
        per_job = single_budget["counters"]
        ceilings = [
            row["headroom"] // row["requested"]
            for row in per_job
            if row["requested"] > 0
        ]
        affordable = min([due_jobs, *ceilings])
        deferred = due_jobs - affordable
    if single_budget["status"] in ("entitlement_unavailable", "accounting_window_unavailable"):
        status = single_budget["status"]
    elif due_jobs == 0:
        status = "no_due_job_candidates"
    elif all(row["requested"] <= row["headroom"] for row in capacity):
        status = "advisory_batch_fits"
    else:
        status = "advisory_batch_exceeds"
    return {
        "status": status,
        "advisory_only": True,
        "max_local_days": MAX_LOCAL_DAYS,
        "due_job_candidates": due_jobs,
        "skipped_day_candidates": skipped_days,
        "affordable_due_job_candidates": affordable,
        "deferred_due_job_candidates": deferred,
        "counters": capacity,
    }
