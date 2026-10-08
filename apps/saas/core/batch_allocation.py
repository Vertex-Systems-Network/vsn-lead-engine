"""Quarantined server-owned v3 identities; no caller, payload intake or settlement."""

import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, eligible_sources
from .models import (
    CandidateEvidence,
    DispatchOperation,
    DispatchReceipt,
    Entitlement,
    Job,
    JobOutbox,
    ResultAcceptance,
    ResultBatch,
    SourceBatchTerminal,
    SourcePolicy,
    UsageCounter,
    UsageReservation,
    User,
    Workspace,
)
from .periods import active_window
from .serializers import SearchSerializer
from .services import membership_for
from .usage import COUNTERS


@transaction.atomic
def allocate_result_batch(user, workspace_id, operation_id, expected_ordinal):
    """Allocate a UUID or replay the same ordinal under a full original-budget lock.

    The ordinal is a compare/replay coordinate; callers never supply the batch UUID.
    Current code cannot start v3 operations. This primitive remains disabled and
    requires a separately reviewed write-ahead path before it becomes reachable.
    """
    if settings.SAAS_BATCH_ALLOCATION_ENABLED is not True:
        raise PermissionDenied("Batch allocation is unavailable.")
    if type(expected_ordinal) is not int or not 1 <= expected_ordinal <= 1000:
        raise ValidationError("A bounded positive batch ordinal is required.")
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    actor = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
    if actor is None or membership_for(actor, workspace_id, lock=True).role not in {
        "owner",
        "admin",
    }:
        raise PermissionDenied("Only current administrators can allocate batch identities.")
    operation = (
        DispatchOperation.objects.select_for_update()
        .filter(pk=operation_id, workspace_id=workspace_id)
        .first()
    )
    if operation is None:
        raise Http404("Workspace resource not found.")
    job = (
        Job.objects.select_for_update()
        .filter(pk=operation.job_id, workspace_id=workspace_id)
        .first()
    )
    intent = JobOutbox.objects.select_for_update().filter(pk=operation.outbox_id, job=job).first()
    if job is None or intent is None:
        raise RevisionConflict()
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    allowed = settings.SAAS_BATCH_ENROLLMENT_SOURCES
    if type(allowed) not in (set, frozenset) or not set(intent.source_snapshot).issubset(allowed):
        raise PermissionDenied("Batch source capability is unavailable.")
    if (
        intent.result_protocol != 3
        or intent.status != "started"
        or job.status not in {"running", "partial"}
        or reservation.status != "reserved"
        or reservation.workspace_id != workspace_id
        or operation.request_hash != job.request_hash
        or operation.attempt.outbox_id != intent.pk
        or operation.attempt.status != "started"
        or operation.status not in {"started", "unknown"}
        or intent.expires_at is not None
        and intent.expires_at <= timezone.now()
        or SourceBatchTerminal.objects.filter(operation=operation).exists()
        or DispatchReceipt.objects.filter(operation__outbox=intent).exists()
        or CandidateEvidence.objects.filter(operation__outbox=intent).exists()
        or ResultAcceptance.objects.filter(operation__outbox=intent).exists()
    ):
        raise RevisionConflict()
    serializer = SearchSerializer(data=job.search)
    serializer.is_valid(raise_exception=True)
    request_hash = hashlib.sha256(
        json.dumps(serializer.validated_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if serializer.validated_data != job.search or request_hash != job.request_hash:
        raise RevisionConflict()
    snapshot, calls = eligible_sources(job.search)
    operations = list(DispatchOperation.objects.filter(outbox=intent).order_by("source_code")[:13])
    policy_calls = dict(
        SourcePolicy.objects.filter(code__in=snapshot).values_list("code", "max_provider_calls")
    )
    if (
        len(operations) > 12
        or snapshot != intent.source_snapshot
        or reservation.leads != job.search["result_limit"]
        or reservation.jobs != 1
        or reservation.exports != 0
        or reservation.provider_calls != calls
        or {op.source_code for op in operations} != set(snapshot)
        or any(
            op.call_limit != policy_calls.get(op.source_code)
            or op.workspace_id != workspace_id
            or op.job_id != job.pk
            or op.request_hash != job.request_hash
            or snapshot.get(op.source_code)
            != {"version": op.policy_version, "hash": op.policy_fingerprint}
            for op in operations
        )
        or operation.call_limit < 1
        or sum(op.call_limit for op in operations) != calls
    ):
        raise RevisionConflict()
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    counter = UsageCounter.objects.select_for_update().get(workspace_id=workspace_id)
    active_window(counter, reservation)
    pending = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    if any(
        getattr(counter, name) + (pending[name] or 0) > getattr(entitlement, limit)
        for name, limit in COUNTERS.items()
    ):
        raise PermissionDenied("Current workspace limits cannot cover reserved use.")
    ordinals = list(
        ResultBatch.objects.filter(operation=operation)
        .order_by("ordinal")
        .values_list("ordinal", flat=True)[:1001]
    )
    if len(ordinals) > 1000 or ordinals != list(range(1, len(ordinals) + 1)):
        raise RevisionConflict()
    total_slots = ResultBatch.objects.filter(operation__outbox=intent).count()
    slot_limit = min(1000, reservation.leads, reservation.provider_calls)
    if (
        len(ordinals) > operation.call_limit
        or total_slots > slot_limit
        or job.result_count > reservation.leads
    ):
        raise RevisionConflict()
    previous = ResultBatch.objects.filter(operation=operation, ordinal=expected_ordinal).first()
    if previous is not None:
        return previous, False
    if operation.status != "started" or expected_ordinal != len(ordinals) + 1:
        raise RevisionConflict()
    # Each eventual accepted batch is nonempty and attests at least one call.
    # Slots are an allocation ceiling only; full capacity remains reserved.
    if len(ordinals) >= operation.call_limit or ResultBatch.objects.filter(
        operation__outbox=intent
    ).count() >= min(1000, reservation.leads, reservation.provider_calls):
        raise ValidationError("Batch identity budget is exhausted.")
    return ResultBatch.objects.create(operation=operation, ordinal=expected_ordinal), True
