"""Tenant-scoped, read-only job-state counts for the workspace overview."""

from django.db.models import Count

from .job_query import JOB_STATES
from .models import Job
from .services import membership_for


def job_status_snapshot(user, workspace_id):
    # Membership is authoritative. No job/lead payload or cross-tenant aggregation.
    membership_for(user, workspace_id)
    counts = dict.fromkeys(JOB_STATES, 0)
    for row in (
        Job.objects.filter(workspace_id=workspace_id)
        .values("status")
        .annotate(number=Count("id"))
    ):
        counts[row["status"]] = row["number"]
    return {
        "workspace_id": str(workspace_id),
        "total": sum(counts.values()),
        "statuses": counts,
    }
