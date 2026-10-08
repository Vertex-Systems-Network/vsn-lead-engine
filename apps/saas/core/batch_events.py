"""Disabled redacted candidate ledger; no accepted payload, R2 grant or settlement."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .batch_candidates import CandidateBatchBinding, verified_batch_candidates
from .models import BatchCandidateEvidence, ResultBatch, SourcePolicy
from .services import IdempotencyConflict


@transaction.atomic
def record_batch_candidates(user, workspace_id, batch_id, body, signature):
    if settings.SAAS_BATCH_CANDIDATE_EVENTS_ENABLED is not True:
        raise PermissionDenied("Batch candidate reconciliation is unavailable.")
    batch = (
        ResultBatch.objects.select_related("operation__job", "operation__outbox")
        .filter(pk=batch_id, operation__workspace_id=workspace_id)
        .first()
    )
    if batch is None:
        raise Http404("Workspace resource not found.")
    # Replay allocation to hold workspace/user/job/source/counter locks and
    # recheck original budgets, current rights, v3 selection and unknown state.
    locked, _ = allocate_result_batch(user, workspace_id, batch.operation_id, batch.ordinal)
    if locked.pk != batch.pk:
        raise IdempotencyConflict()
    operation = locked.operation
    binding = CandidateBatchBinding(
        operation.workspace_id,
        operation.job_id,
        operation.id,
        batch.id,
        operation.provider_key,
        operation.source_code,
        operation.request_hash,
        operation.policy_fingerprint,
        operation.created_at,
        operation.outbox.reservation.leads,
    )
    policy = SourcePolicy.objects.get(pk=operation.source_code)
    proof = verified_batch_candidates(body, signature, binding, policy, operation.job.search)
    previous = BatchCandidateEvidence.objects.select_for_update().filter(batch=batch).first()
    if previous is not None:
        if (
            previous.body_hash,
            previous.source_code,
            previous.event_ref,
            previous.candidate_count,
            previous.earliest_delete_at,
        ) != (
            proof.body_hash,
            operation.source_code,
            proof.event_ref,
            proof.candidate_count,
            proof.earliest_delete_at,
        ):
            raise IdempotencyConflict()
        return previous, False
    # Unknown effects may replay already recorded evidence, but cannot add a new
    # event. Resolve them through a separately attested reconciliation path.
    if operation.status != "started":
        raise ValidationError("Unknown batch effects require reconciliation.")
    try:
        with transaction.atomic():
            evidence = BatchCandidateEvidence.objects.create(
                batch=batch,
                source_code=operation.source_code,
                event_ref=proof.event_ref,
                body_hash=proof.body_hash,
                candidate_count=proof.candidate_count,
                earliest_delete_at=proof.earliest_delete_at,
            )
    except IntegrityError:
        raise IdempotencyConflict() from None
    return evidence, True
