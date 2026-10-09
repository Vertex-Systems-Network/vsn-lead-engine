"""Default-off atomic accounting for explicit v3 source outcomes."""

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import PermissionDenied

from .batch_reconciliation_read import inspect_batch_reconciliation
from .jobs import RevisionConflict, locked_job
from .models import (
    DispatchOperation,
    Entitlement,
    JobAttempt,
    JobOutbox,
    UsageCounter,
    UsageReservation,
)
from .periods import active_window
from .usage import COUNTERS, _settle_locked


@transaction.atomic
def settle_reconciled_batch_job(user, workspace_id, job_id, source_proofs):
    """Commit exact current mixed or positive source evidence once.

    Every original operation needs a prior durable signed positive-final or
    zero-effect outcome. At least one accepted positive source is required;
    all-zero outcomes retain the reservation for separate business resolution.
    This internal service has no route or worker and cannot activate dispatch.
    """
    if settings.SAAS_BATCH_RECONCILIATION_SETTLEMENT_ENABLED is not True:
        raise PermissionDenied("Batch reconciliation settlement is unavailable.")
    # The inspection locks the job, original reservation and every operation,
    # replays current rights and signed durable evidence in this transaction.
    actual = inspect_batch_reconciliation(user, workspace_id, job_id, source_proofs)
    if not actual.positive_operation_ids:
        raise RevisionConflict()
    job = locked_job(user, workspace_id, job_id)
    intent = JobOutbox.objects.select_for_update().get(job=job)
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    entitlement = Entitlement.objects.select_for_update().get(workspace_id=workspace_id)
    counter = UsageCounter.objects.select_for_update().get(workspace_id=workspace_id)
    active_window(counter, reservation)
    if job.revision >= 2147483647:
        raise RevisionConflict()
    pending = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    if any(
        getattr(counter, name) + (pending[name] or 0) > getattr(entitlement, limit)
        for name, limit in COUNTERS.items()
    ):
        raise PermissionDenied("Current workspace limits cannot cover reserved use.")
    operation_ids = actual.positive_operation_ids + actual.noeffect_operation_ids
    if DispatchOperation.objects.filter(
        pk__in=operation_ids, status__in=["started", "unknown"]
    ).count() != len(operation_ids):
        raise RevisionConflict()
    attempts = set(
        DispatchOperation.objects.filter(pk__in=operation_ids).values_list("attempt_id", flat=True)
    )
    if len(attempts) != 1:
        raise RevisionConflict()
    attempt = JobAttempt.objects.select_for_update().get(pk=attempts.pop())
    if attempt.outbox_id != intent.pk or attempt.status != "started":
        raise RevisionConflict()
    _settle_locked(
        reservation,
        {"leads": actual.leads, "jobs": 1, "provider_calls": actual.provider_calls, "exports": 0},
    )
    DispatchOperation.objects.filter(pk__in=actual.positive_operation_ids).update(status="success")
    DispatchOperation.objects.filter(pk__in=actual.noeffect_operation_ids).update(status="noeffect")
    attempt.status = "done"
    attempt.save(update_fields=["status"])
    intent.status = "done"
    intent.save(update_fields=["status", "updated_at"])
    job.status = "completed"
    job.result_count = actual.leads
    job.revision += 1
    job.save(update_fields=["status", "result_count", "revision", "updated_at"])
    return job, True
