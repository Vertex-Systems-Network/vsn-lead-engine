"""Tenant-scoped, read-only operational counts for owners and administrators.

Counts are observational snapshots, not a lock-consistent deployment or
provider-rights certification. No source, job, membership or usage mutation.
"""

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .job_query import JOB_STATES
from .models import (
    DispatchOperation,
    Job,
    JobOutbox,
    Membership,
    UsageReservation,
    WorkspaceInvitation,
)
from .services import membership_for

ROLES = ("owner", "admin", "member", "viewer")
OUTBOX_STATES = ("pending", "cancelled", "started", "done")


def status_counts(query, statuses):
    counts = dict.fromkeys(statuses, 0)
    for item in query.values("status").annotate(total=Count("pk")):
        if item["status"] in counts:
            counts[item["status"]] = item["total"]
    return counts


def operational_health(actor, workspace_id):
    current = membership_for(actor, workspace_id)
    if current.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners and administrators may review operations.")
    now = timezone.now()
    role_counts = dict.fromkeys(ROLES, 0)
    for row in (
        Membership.objects.filter(workspace_id=workspace_id)
        .values("role")
        .annotate(total=Count("pk"))
    ):
        if row["role"] in role_counts:
            role_counts[row["role"]] = row["total"]
    invitations = WorkspaceInvitation.objects.filter(workspace_id=workspace_id)
    invite_counts = invitations.aggregate(
        pending=Count(
            "pk",
            filter=Q(
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=now,
            ),
        ),
        accepted=Count("pk", filter=Q(accepted_at__isnull=False)),
        revoked=Count(
            "pk", filter=Q(accepted_at__isnull=True, revoked_at__isnull=False)
        ),
        expired=Count(
            "pk",
            filter=Q(
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__lte=now,
            ),
        ),
    )
    outboxes = JobOutbox.objects.filter(job__workspace_id=workspace_id)
    return {
        "workspace_id": str(workspace_id),
        "member_roles": role_counts,
        "invitations": invite_counts,
        "jobs": status_counts(Job.objects.filter(workspace_id=workspace_id), JOB_STATES),
        "outboxes": status_counts(outboxes, OUTBOX_STATES),
        "expired_pending_outboxes": outboxes.filter(
            status="pending", expires_at__isnull=False, expires_at__lte=now
        ).count(),
        "unknown_dispatch_operations": DispatchOperation.objects.filter(
            workspace_id=workspace_id, status="unknown"
        ).count(),
        "reserved_usage_intents": UsageReservation.objects.filter(
            workspace_id=workspace_id, status="reserved"
        ).count(),
        "advisory_only": True,
    }
