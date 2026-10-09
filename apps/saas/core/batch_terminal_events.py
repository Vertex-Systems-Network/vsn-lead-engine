"""Disabled source-final evidence; no whole-job settlement or quota release."""

import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .billing_evidence import unique_object
from .jobs import RevisionConflict
from .models import (
    AcceptedResult,
    BatchAcceptance,
    ResultBatch,
    SourceBatchNoEffect,
    SourceBatchTerminal,
)
from .services import IdempotencyConflict
from .terminal_manifest import TerminalBatch, TerminalBinding, verified_terminal_manifest


@transaction.atomic
def record_source_batch_terminal(user, workspace_id, operation_id, body, signature):
    """Bind a signed source-final set to every allocated, accepted batch once.

    Empty or unaccepted allocations and unknown effects remain unresolved. No
    attempt, operation, job, reservation or counter changes happen here.
    """
    if settings.SAAS_BATCH_TERMINAL_EVENTS_ENABLED is not True:
        raise PermissionDenied("Source-final reconciliation is unavailable.")
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
    if SourceBatchNoEffect.objects.filter(operation=operation).exists():
        raise RevisionConflict()
    reservation = operation.outbox.reservation
    batches = list(
        ResultBatch.objects.select_for_update()
        .filter(operation=operation)
        .order_by("ordinal")[:1001]
    )
    if not batches or len(batches) > 1000:
        raise RevisionConflict()
    acceptances = list(
        BatchAcceptance.objects.select_for_update()
        .select_related("candidate")
        .filter(candidate__batch__operation=operation)
    )
    accepted = {item.candidate.batch_id: item for item in acceptances}
    if len(accepted) != len(batches) or any(
        batch.ordinal != position or batch.pk not in accepted
        for position, batch in enumerate(batches, 1)
    ):
        raise ValidationError("Every allocated source batch needs exact accepted evidence.")
    total_leads = total_calls = 0
    for batch in batches:
        acceptance = accepted[batch.pk]
        candidate = acceptance.candidate
        if (
            candidate.source_code != operation.source_code
            or acceptance.source_code != operation.source_code
            or candidate.candidate_count != acceptance.accepted_count
            or AcceptedResult.objects.filter(batch_acceptance=acceptance).count()
            != acceptance.accepted_count
        ):
            raise RevisionConflict()
        total_leads += acceptance.accepted_count
        total_calls += acceptance.provider_calls
    if (
        total_leads > reservation.leads
        or total_calls > operation.call_limit
        or total_calls > reservation.provider_calls
    ):
        raise ValidationError("Source batch totals exceed original capacity.")
    binding = TerminalBinding(
        operation.workspace_id,
        operation.job_id,
        operation.id,
        operation.provider_key,
        operation.source_code,
        operation.request_hash,
        operation.policy_fingerprint,
        reservation.leads,
        operation.call_limit,
        tuple(
            TerminalBatch(
                batch.pk,
                accepted[batch.pk].body_hash,
                accepted[batch.pk].accepted_count,
                accepted[batch.pk].provider_calls,
            )
            for batch in batches
        ),
    )
    proof = verified_terminal_manifest(body, signature, binding)
    data = json.loads(body, object_pairs_hook=unique_object)
    previous = SourceBatchTerminal.objects.select_for_update().filter(operation=operation).first()
    if previous is not None:
        if (
            previous.body_hash,
            previous.batch_set_hash,
            previous.batch_count,
            previous.accepted_count,
            previous.provider_calls,
            previous.receipt_ref,
            previous.source_code,
        ) != (
            proof.body_hash,
            proof.batch_set_hash,
            proof.batch_count,
            proof.accepted_count,
            proof.provider_calls,
            proof.receipt_ref,
            operation.source_code,
        ):
            raise IdempotencyConflict()
        return previous, False
    if operation.status != "started" or any(
        item.candidate.earliest_delete_at <= timezone.now() for item in acceptances
    ):
        raise ValidationError("Unknown or expired source effects require reconciliation.")
    try:
        with transaction.atomic():
            event = SourceBatchTerminal.objects.create(
                operation=operation,
                source_code=operation.source_code,
                receipt_ref=proof.receipt_ref,
                source_key_id=data["source_key_id"],
                body_hash=proof.body_hash,
                batch_set_hash=proof.batch_set_hash,
                batch_count=proof.batch_count,
                accepted_count=proof.accepted_count,
                provider_calls=proof.provider_calls,
                issued_at=proof.issued_at,
            )
    except IntegrityError:
        raise IdempotencyConflict() from None
    return event, True
