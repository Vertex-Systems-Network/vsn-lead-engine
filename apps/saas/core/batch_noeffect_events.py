"""Default-off v3 source zero-effect evidence, without settlement or refund."""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .batch_noeffect_manifest import NoEffectBatch, NoEffectBinding, verified_noeffect_manifest
from .jobs import RevisionConflict
from .models import (
    AcceptedResult,
    BatchAcceptance,
    BatchCandidateEvidence,
    DispatchReceipt,
    ResultAcceptance,
    ResultBatch,
    SourceBatchNoEffect,
    SourceBatchTerminal,
)
from .services import IdempotencyConflict


@transaction.atomic
def record_source_batch_noeffect(user, workspace_id, operation_id, body, signature):
    """Record exact source evidence while retaining all original reservations.

    At least one server-owned identity is required. The pure proof supports an
    empty set, but a zero-allocation operation has no write-ahead batch identity
    to reconcile in this service and must remain unresolved.
    """
    if settings.SAAS_BATCH_NOEFFECT_EVENTS_ENABLED is not True:
        raise PermissionDenied("Source zero-effect evidence is unavailable.")
    first = (
        ResultBatch.objects.filter(operation_id=operation_id, operation__workspace_id=workspace_id)
        .order_by("ordinal")
        .first()
    )
    if first is None:
        raise Http404("Workspace batch source not found.")
    locked, _ = allocate_result_batch(
        user, workspace_id, operation_id, first.ordinal, terminal_replay=True
    )
    if locked.pk != first.pk or first.ordinal != 1:
        raise RevisionConflict()
    operation = locked.operation
    if (
        DispatchReceipt.objects.filter(operation=operation).exists()
        or ResultAcceptance.objects.filter(operation=operation).exists()
        or SourceBatchTerminal.objects.filter(operation=operation).exists()
    ):
        raise RevisionConflict()
    batches = list(
        ResultBatch.objects.select_for_update()
        .filter(operation=operation)
        .order_by("ordinal")[:1001]
    )
    if not batches or len(batches) > 1000 or any(
        item.ordinal != position for position, item in enumerate(batches, 1)
    ):
        raise RevisionConflict()
    candidates = list(
        BatchCandidateEvidence.objects.select_for_update().filter(batch__operation=operation)
    )
    by_batch = {item.batch_id: item for item in candidates}
    batch_ids = {batch.pk for batch in batches}
    if len(by_batch) != len(candidates) or any(
        item.source_code != operation.source_code or item.batch_id not in batch_ids
        for item in candidates
    ):
        raise RevisionConflict()
    if (
        BatchAcceptance.objects.filter(candidate__batch__operation=operation).exists()
        or AcceptedResult.objects.filter(batch_acceptance__candidate__batch__operation=operation).exists()
    ):
        raise ValidationError("Accepted source effects require positive reconciliation.")
    proof = verified_noeffect_manifest(
        body,
        signature,
        NoEffectBinding(
            operation.workspace_id,
            operation.job_id,
            operation.id,
            operation.provider_key,
            operation.source_code,
            operation.request_hash,
            operation.policy_fingerprint,
            tuple(
                NoEffectBatch(
                    batch.pk, by_batch[batch.pk].body_hash if batch.pk in by_batch else None
                )
                for batch in batches
            ),
        ),
    )
    previous = SourceBatchNoEffect.objects.select_for_update().filter(operation=operation).first()
    if previous is not None:
        if (
            previous.source_code,
            previous.receipt_ref,
            previous.source_key_id,
            previous.body_hash,
            previous.batch_set_hash,
            previous.batch_count,
            previous.provider_calls,
        ) != (
            operation.source_code,
            proof.receipt_ref,
            proof.key_id,
            proof.body_hash,
            proof.batch_set_hash,
            proof.batch_count,
            0,
        ):
            raise IdempotencyConflict()
        return previous, False
    try:
        with transaction.atomic():
            event = SourceBatchNoEffect.objects.create(
                operation=operation,
                source_code=operation.source_code,
                receipt_ref=proof.receipt_ref,
                source_key_id=proof.key_id,
                body_hash=proof.body_hash,
                batch_set_hash=proof.batch_set_hash,
                batch_count=proof.batch_count,
                provider_calls=0,
                issued_at=proof.issued_at,
            )
    except IntegrityError:
        raise IdempotencyConflict() from None
    return event, True
