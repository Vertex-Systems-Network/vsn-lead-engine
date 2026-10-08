"""Disabled atomic v3 batch intake; reservation and job settlement remain separate."""

import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .batch_candidates import CandidateBatchBinding
from .batch_payload import verified_batch_payload
from .billing_evidence import unique_object
from .jobs import RevisionConflict
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    BatchAcceptance,
    BatchCandidateEvidence,
    ResultBatch,
    SourcePolicy,
)
from .services import IdempotencyConflict


@transaction.atomic
def accept_result_batch(
    user,
    workspace_id,
    batch_id,
    candidate_body,
    candidate_signature,
    body,
    source_signature,
    dedupe_signature,
):
    """Persist one paired batch exactly once, retaining the entire reservation.

    No external caller, dispatch path, usage settlement or finality follows from
    this service. An unknown-effect operation can only replay an existing exact
    acceptance. Actual isolated R2 authority is still a separate launch gate.
    """
    if settings.SAAS_BATCH_ACCEPTANCE_ENABLED is not True:
        raise PermissionDenied("Batch acceptance is unavailable.")
    batch = (
        ResultBatch.objects.select_related("operation")
        .filter(pk=batch_id, operation__workspace_id=workspace_id)
        .first()
    )
    if batch is None:
        raise Http404("Workspace resource not found.")
    # Reuse the enrollment, actor, source, period, entitlement, original budget
    # and lock order of allocation. It returns an existing identity on replay.
    locked, _ = allocate_result_batch(user, workspace_id, batch.operation_id, batch.ordinal)
    if locked.pk != batch.pk:
        raise IdempotencyConflict()
    operation = locked.operation
    intent = operation.outbox
    reservation = intent.reservation
    job = operation.job
    policy = SourcePolicy.objects.get(pk=operation.source_code)
    binding = CandidateBatchBinding(
        operation.workspace_id,
        operation.job_id,
        operation.id,
        locked.id,
        operation.provider_key,
        operation.source_code,
        operation.request_hash,
        operation.policy_fingerprint,
        operation.created_at,
        reservation.leads,
    )
    namespace = f"saas-results/v1/{workspace_id}"
    review, proof, records = verified_batch_payload(
        candidate_body,
        candidate_signature,
        body,
        source_signature,
        dedupe_signature,
        binding,
        namespace,
        operation.call_limit,
        policy,
        job.search,
    )
    candidate = (
        BatchCandidateEvidence.objects.select_for_update().filter(batch=locked).first()
    )
    if candidate is None or (
        candidate.source_code,
        candidate.event_ref,
        candidate.body_hash,
        candidate.candidate_count,
        candidate.earliest_delete_at,
    ) != (
        operation.source_code,
        review.event_ref,
        review.body_hash,
        review.candidate_count,
        review.earliest_delete_at,
    ):
        raise ValidationError("Recorded batch candidate evidence is unavailable or changed.")
    data = json.loads(body, object_pairs_hook=unique_object)
    previous = BatchAcceptance.objects.select_for_update().filter(candidate=candidate).first()
    if previous is not None:
        if (
            previous.body_hash,
            previous.receipt_ref,
            previous.accepted_count,
            previous.provider_calls,
            previous.namespace,
        ) != (
            proof.body_hash,
            proof.receipt_ref,
            len(records),
            proof.provider_calls,
            namespace,
        ):
            raise IdempotencyConflict()
        return previous, False
    if operation.status != "started" or review.earliest_delete_at <= timezone.now():
        raise ValidationError("Unknown or expired batch effects require reconciliation.")
    if job.result_count != 0:
        raise RevisionConflict()
    totals = BatchAcceptance.objects.filter(
        candidate__batch__operation__outbox=intent
    ).aggregate(leads=Sum("accepted_count"), calls=Sum("provider_calls"))
    source_calls = BatchAcceptance.objects.filter(
        candidate__batch__operation=operation
    ).aggregate(calls=Sum("provider_calls"))["calls"] or 0
    if (
        (totals["leads"] or 0) + len(records) > reservation.leads
        or (totals["calls"] or 0) + proof.provider_calls > reservation.provider_calls
        or source_calls + proof.provider_calls > operation.call_limit
    ):
        raise ValidationError("Batch totals exceed the original reserved capacity.")
    try:
        with transaction.atomic():
            acceptance = BatchAcceptance.objects.create(
                candidate=candidate,
                source_code=operation.source_code,
                receipt_ref=proof.receipt_ref,
                source_key_id=data["source_key_id"],
                dedupe_key_id=data["dedupe_key_id"],
                body_hash=proof.body_hash,
                namespace=namespace,
                accepted_count=len(records),
                provider_calls=proof.provider_calls,
                issued_at=proof.issued_at,
            )
            for position, row in enumerate(records, 1):
                result = AcceptedResult.objects.create(
                    workspace_id=workspace_id,
                    job=job,
                    batch_acceptance=acceptance,
                    batch_position=position,
                    record_ref=row.record_ref,
                    country=row.country,
                    category=row.category,
                    fields=dict(row.fields),
                    field_lineage=dict(row.field_lineage),
                    observed_at=row.observed_at,
                    delete_at=row.delete_at,
                    purpose=row.purpose,
                    retention_version=row.retention_version,
                )
                AcceptedFingerprint.objects.bulk_create(
                    [
                        AcceptedFingerprint(workspace_id=workspace_id, result=result, token=token)
                        for token in row.tokens
                    ]
                )
            if review.earliest_delete_at <= timezone.now():
                raise ValidationError("Candidate eligibility expired during intake.")
    except IntegrityError:
        raise IdempotencyConflict() from None
    return acceptance, True
