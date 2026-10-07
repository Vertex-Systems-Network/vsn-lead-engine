"""Bounded internal pre-dispatch leases, never a provider execution authorization."""

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, eligible_sources
from .models import Entitlement, JobAttempt, JobOutbox, UsageCounter, UsageReservation, Workspace
from .serializers import SearchSerializer
from .usage import COUNTERS, lock_workspace

LEASE = timedelta(seconds=60)
MAX_ATTEMPTS = 3


def preflight(outbox):
    """Caller holds the workspace lock; repeat before every future external action."""
    job = outbox.job
    lock_workspace(outbox.submitted_by, job.workspace_id)
    if job.status != "queued" or outbox.status != "pending":
        raise RevisionConflict()
    reservation = UsageReservation.objects.select_for_update().get(pk=outbox.reservation_id)
    if reservation.workspace_id != job.workspace_id or reservation.status != "reserved":
        raise RevisionConflict()
    entitlement = (
        Entitlement.objects.select_for_update().filter(workspace_id=job.workspace_id).first()
    )
    if entitlement is None or not entitlement.active:
        raise PermissionDenied("Workspace entitlement is inactive.")
    serializer = SearchSerializer(data=job.search)
    serializer.is_valid(raise_exception=True)
    request_hash = hashlib.sha256(
        json.dumps(serializer.validated_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if serializer.validated_data != job.search or request_hash != job.request_hash:
        raise RevisionConflict()
    if (
        reservation.leads != job.search["result_limit"]
        or reservation.jobs != 1
        or reservation.exports != 0
    ):
        raise RevisionConflict()
    snapshot, calls = eligible_sources(job.search)
    if snapshot != outbox.source_snapshot or calls != reservation.provider_calls:
        raise PermissionDenied("Source policy changed; this intent cannot dispatch.")
    # An administrator can reduce a cap after enqueue. Include all outstanding
    # reservations and settled usage rather than trusting the historical snapshot.
    counter = UsageCounter.objects.get(workspace_id=job.workspace_id)
    pending = UsageReservation.objects.filter(
        workspace_id=job.workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    for name, limit in COUNTERS.items():
        if getattr(counter, name) + (pending[name] or 0) > getattr(entitlement, limit):
            raise PermissionDenied("Current usage exceeds workspace entitlement.")


@transaction.atomic
def claim_pre_dispatch(outbox_id):
    """Trusted internal caller only. Fixed lease; no heartbeat, retry loop or consumer."""
    intent = JobOutbox.objects.select_related("job", "submitted_by").get(pk=outbox_id)
    Workspace.objects.select_for_update().get(pk=intent.job.workspace_id)
    intent = (
        JobOutbox.objects.select_for_update()
        .select_related("job", "submitted_by")
        .get(pk=outbox_id)
    )
    preflight(intent)
    now = timezone.now()
    active = JobAttempt.objects.select_for_update().filter(outbox=intent, status="leased").first()
    if active:
        if active.expires_at > now:
            raise RevisionConflict()
        active.status = "expired"
        active.save(update_fields=["status"])
    count = JobAttempt.objects.filter(outbox=intent).count()
    if count >= MAX_ATTEMPTS:
        raise ValidationError(
            "Pre-dispatch attempt budget exhausted; cancel and review this intent."
        )
    return JobAttempt.objects.create(
        outbox=intent, number=count + 1, job_revision=intent.job.revision, expires_at=now + LEASE
    )


@transaction.atomic
def check_pre_dispatch(outbox_id, token):
    """Validate current fencing and gates. This method performs no external action."""
    intent = JobOutbox.objects.select_related("job", "submitted_by").get(pk=outbox_id)
    Workspace.objects.select_for_update().get(pk=intent.job.workspace_id)
    intent = (
        JobOutbox.objects.select_for_update()
        .select_related("job", "submitted_by")
        .get(pk=outbox_id)
    )
    attempt = (
        JobAttempt.objects.select_for_update()
        .filter(outbox=intent, token=token, status="leased")
        .first()
    )
    if (
        attempt is None
        or attempt.expires_at <= timezone.now()
        or attempt.job_revision != intent.job.revision
    ):
        raise RevisionConflict()
    preflight(intent)
    if attempt.expires_at <= timezone.now():
        raise RevisionConflict()
    return attempt
