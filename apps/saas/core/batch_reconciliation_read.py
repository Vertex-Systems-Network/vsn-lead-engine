"""Read-only all-source v3 evidence preflight; no refund or settlement."""

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_noeffect_events import record_source_batch_noeffect
from .batch_reconciliation import SourceEvidenceTotals, bounded_source_evidence
from .batch_terminal_events import record_source_batch_terminal
from .jobs import RevisionConflict, eligible_sources, locked_job
from .models import (
    AcceptedResult,
    BatchAcceptance,
    DispatchOperation,
    Entitlement,
    JobAttempt,
    JobOutbox,
    SourceBatchNoEffect,
    SourceBatchTerminal,
    UsageReservation,
)
from .services import membership_for


@transaction.atomic
def inspect_batch_reconciliation(user, workspace_id, job_id, source_proofs):
    """Revalidate one already recorded signed outcome per original source.

    Every source must have a prior durable positive-final or no-effect record.
    The underlying replay services lock current rights and compare fresh exact
    signed bytes with all allocated identities. This returns bounded evidence
    totals only; an unknown operation stays unknown and use stays reserved.
    """
    if settings.SAAS_BATCH_RECONCILIATION_READ_ENABLED is not True:
        raise PermissionDenied("Batch reconciliation preflight is unavailable.")
    job = locked_job(user, workspace_id, job_id)
    if membership_for(user, workspace_id, lock=True).role not in {"owner", "admin"}:
        raise PermissionDenied("Only current administrators may inspect reconciliation.")
    intent = JobOutbox.objects.select_for_update().filter(job=job).first()
    if intent is None:
        raise Http404("Workspace resource not found.")
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    snapshot, original_calls = eligible_sources(job.search)
    operations = list(
        DispatchOperation.objects.select_for_update()
        .filter(outbox=intent, workspace_id=workspace_id, job=job)
        .order_by("source_code")[:13]
    )
    if (
        intent.result_protocol != 3
        or intent.status != "started"
        or job.status not in {"running", "partial"}
        or job.result_count != 0
        or reservation.status != "reserved"
        or reservation.workspace_id != workspace_id
        or reservation.jobs != 1
        or reservation.exports != 0
        or reservation.leads != job.search["result_limit"]
        or reservation.provider_calls != original_calls
        or intent.source_snapshot != snapshot
        or not 1 <= len(operations) <= 12
        or len({op.source_code for op in operations}) != len(operations)
        or {op.source_code for op in operations} != set(snapshot)
        or type(source_proofs) is not dict
        or set(source_proofs) != {op.pk for op in operations}
        or any(
            op.status not in {"started", "unknown"}
            or op.request_hash != job.request_hash
            or op.workspace_id != workspace_id
            or op.job_id != job.pk
            or snapshot[op.source_code]
            != {"version": op.policy_version, "hash": op.policy_fingerprint}
            for op in operations
        )
    ):
        raise RevisionConflict()
    attempts = {op.attempt_id for op in operations}
    if len(attempts) != 1:
        raise RevisionConflict()
    attempt = JobAttempt.objects.select_for_update().get(pk=attempts.pop())
    if attempt.outbox_id != intent.pk or attempt.status != "started":
        raise RevisionConflict()
    sources = []
    for op in operations:
        supplied = source_proofs[op.pk]
        if (
            type(supplied) is not tuple
            or len(supplied) != 2
            or not isinstance(supplied[0], bytes)
            or not isinstance(supplied[1], str)
        ):
            raise ValidationError("Exact current source proof is required.")
        final = SourceBatchTerminal.objects.select_for_update().filter(operation=op).first()
        zero = SourceBatchNoEffect.objects.select_for_update().filter(operation=op).first()
        if (final is None) == (zero is None):
            raise RevisionConflict()
        if final is not None:
            replay, created = record_source_batch_terminal(
                user, workspace_id, op.pk, supplied[0], supplied[1]
            )
            if created or replay.pk != final.pk:
                raise RevisionConflict()
            aggregate = BatchAcceptance.objects.filter(
                candidate__batch__operation=op
            ).aggregate(calls=Sum("provider_calls"))
            committed = aggregate["calls"] or 0
            if AcceptedResult.objects.filter(
                batch_acceptance__candidate__batch__operation=op,
                workspace_id=workspace_id,
                job=job,
            ).count() != final.accepted_count:
                raise RevisionConflict()
            sources.append(
                SourceEvidenceTotals(
                    op.pk,
                    op.source_code,
                    op.status,
                    "source-final",
                    op.call_limit,
                    final.batch_count,
                    final.accepted_count,
                    committed,
                    final.provider_calls,
                )
            )
        else:
            replay, created = record_source_batch_noeffect(
                user, workspace_id, op.pk, supplied[0], supplied[1]
            )
            if created or replay.pk != zero.pk:
                raise RevisionConflict()
            sources.append(
                SourceEvidenceTotals(
                    op.pk,
                    op.source_code,
                    op.status,
                    "source-noeffect",
                    op.call_limit,
                    zero.batch_count,
                    0,
                    0,
                    0,
                )
            )
    totals = bounded_source_evidence(
        tuple(sources), frozenset(snapshot), reservation.leads, reservation.provider_calls
    )
    if AcceptedResult.objects.filter(
        workspace_id=workspace_id, job=job, batch_acceptance__isnull=False
    ).count() != totals.leads:
        raise RevisionConflict()
    return totals
