"""Default-off all-source v3 settlement; ordinary dispatch remains quarantined."""

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_accounting import SourceAccounting, checked_batch_settlement
from .batch_terminal_events import record_source_batch_terminal
from .jobs import RevisionConflict, eligible_sources, locked_job
from .models import (
    BatchAcceptance,
    DispatchOperation,
    Entitlement,
    JobAttempt,
    JobOutbox,
    SourceBatchTerminal,
    UsageCounter,
    UsageReservation,
)
from .periods import active_window
from .services import membership_for
from .usage import COUNTERS, _settle_locked


@transaction.atomic
def settle_batch_job(user, workspace_id, job_id, terminal_proofs):
    """Commit one positive-result job only after current exact source proofs.

    No empty/no-effect or unknown operation is eligible. A repeated call after
    settlement fails closed without charging again; replay/recovery needs a
    separately reviewed settled-state proof path. No API or worker calls this.
    """
    if settings.SAAS_BATCH_SETTLEMENT_ENABLED is not True:
        raise PermissionDenied("Batch job settlement is unavailable.")
    job = locked_job(user, workspace_id, job_id)
    if membership_for(user, workspace_id, lock=True).role not in {"owner", "admin"}:
        raise PermissionDenied("Only current administrators may settle batch jobs.")
    intent = JobOutbox.objects.select_for_update().filter(job=job).first()
    if intent is None:
        raise Http404("Workspace resource not found.")
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    counter = UsageCounter.objects.select_for_update().get(workspace_id=workspace_id)
    active_window(counter, reservation)
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
        or job.revision >= 2147483647
        or reservation.status != "reserved"
        or reservation.workspace_id != workspace_id
        or reservation.jobs != 1
        or reservation.exports != 0
        or reservation.leads != job.search["result_limit"]
        or reservation.provider_calls != original_calls
        or intent.source_snapshot != snapshot
        or not 1 <= len(operations) <= 12
        or {op.source_code for op in operations} != set(snapshot)
        or any(op.status != "started" or op.request_hash != job.request_hash for op in operations)
        or type(terminal_proofs) is not dict
        or set(terminal_proofs) != {op.pk for op in operations}
    ):
        raise RevisionConflict()
    attempts = {op.attempt_id for op in operations}
    if len(attempts) != 1:
        raise RevisionConflict()
    attempt = JobAttempt.objects.select_for_update().get(pk=attempts.pop())
    if attempt.outbox_id != intent.pk or attempt.status != "started":
        raise RevisionConflict()
    pending = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    if any(
        getattr(counter, name) + (pending[name] or 0) > getattr(entitlement, limit)
        for name, limit in COUNTERS.items()
    ):
        raise PermissionDenied("Current workspace limits cannot cover reserved use.")
    sources = []
    for op in operations:
        proof = terminal_proofs[op.pk]
        if (
            type(proof) is not tuple
            or len(proof) != 2
            or not isinstance(proof[0], bytes)
            or not isinstance(proof[1], str)
            or not SourceBatchTerminal.objects.filter(operation=op).exists()
        ):
            raise ValidationError("Current exact source-final proof is required.")
        final, created = record_source_batch_terminal(user, workspace_id, op.pk, proof[0], proof[1])
        if created:
            raise RevisionConflict()
        committed = (
            BatchAcceptance.objects.filter(candidate__batch__operation=op).aggregate(
                calls=Sum("provider_calls")
            )["calls"]
            or 0
        )
        sources.append(
            SourceAccounting(
                op.pk,
                op.source_code,
                op.status,
                op.call_limit,
                final.batch_count,
                final.accepted_count,
                committed,
                final.provider_calls,
            )
        )
    actual = checked_batch_settlement(
        tuple(sources), frozenset(snapshot), reservation.leads, reservation.provider_calls
    )
    _settle_locked(
        reservation,
        {
            "leads": actual.leads,
            "jobs": actual.jobs,
            "provider_calls": actual.provider_calls,
            "exports": actual.exports,
        },
    )
    DispatchOperation.objects.filter(pk__in=actual.operation_ids, status="started").update(
        status="success"
    )
    attempt.status = "done"
    attempt.save(update_fields=["status"])
    intent.status = "done"
    intent.save(update_fields=["status", "updated_at"])
    job.status = "completed"
    job.result_count = actual.leads
    job.revision += 1
    job.save(update_fields=["status", "result_count", "revision", "updated_at"])
    return job, True
