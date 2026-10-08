"""Durable redacted candidate-event comparison, without result acceptance."""

from django.db import IntegrityError, transaction

from .models import CandidateEvidence, DispatchOperation
from .result_evidence import review_candidates
from .services import IdempotencyConflict


@transaction.atomic
def record_candidate_review(user, workspace_id, operation_id, body, signature):
    """One bounded event per operation. Current rights/role rechecked on every replay.

    The nested preflight holds workspace/operation/policy locks to transaction end.
    A source event cannot cross operation/tenant boundaries, even with valid keys.
    No input payload, signature, credential or raw source record ID is retained.
    This is an audit comparison record; it cannot settle usage or establish R2
    uniqueness, and must not be treated as an accepted-lead receipt.
    """
    review = review_candidates(user, workspace_id, operation_id, body, signature)
    operation = DispatchOperation.objects.get(pk=operation_id, workspace_id=workspace_id)
    previous = CandidateEvidence.objects.filter(operation=operation).first()
    if previous is not None:
        if previous.body_hash != review.body_hash:
            raise IdempotencyConflict()
        return previous, False
    try:
        with transaction.atomic():
            evidence = CandidateEvidence.objects.create(
                operation=operation,
                source_code=operation.source_code,
                event_ref=review.event_ref,
                body_hash=review.body_hash,
                candidate_count=review.candidate_count,
                earliest_delete_at=review.earliest_delete_at,
            )
    except IntegrityError:
        raise IdempotencyConflict() from None
    return evidence, True
