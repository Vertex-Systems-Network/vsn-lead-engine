"""Default-off read-only exact replay of an already settled positive v3 job."""

from django.conf import settings
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, eligible_sources, locked_job
from .models import (
    AcceptedResult,
    BatchAcceptance,
    DispatchOperation,
    Entitlement,
    JobAttempt,
    JobOutbox,
    ResultBatch,
    SourceBatchTerminal,
    UsageReservation,
)
from .services import IdempotencyConflict, membership_for
from .terminal_manifest import TerminalBatch, TerminalBinding, verified_terminal_manifest


@transaction.atomic
def replay_settled_batch_job(user, workspace_id, job_id, terminal_proofs):
    """Prove exact settled evidence again; never update a counter or state.

    Only current 24-hour source-final proof is accepted. Expired signatures,
    changed source rights, missing batches or ambiguous states fail closed.
    No API or worker calls this internal service.
    """
    if settings.SAAS_BATCH_SETTLED_REPLAY_ENABLED is not True:
        raise PermissionDenied("Settled batch replay is unavailable.")
    job = locked_job(user, workspace_id, job_id)
    if membership_for(user, workspace_id, lock=True).role not in {"owner", "admin"}:
        raise PermissionDenied("Only current administrators may replay settled evidence.")
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
        or intent.status != "done"
        or job.status != "completed"
        or not 1 <= job.result_count <= 1000
        or reservation.status != "settled"
        or reservation.workspace_id != workspace_id
        or reservation.leads != job.search["result_limit"]
        or reservation.provider_calls != original_calls
        or intent.source_snapshot != snapshot
        or not 1 <= len(operations) <= 12
        or len({op.source_code for op in operations}) != len(operations)
        or {op.source_code for op in operations} != set(snapshot)
        or type(terminal_proofs) is not dict
        or set(terminal_proofs) != {op.pk for op in operations}
        or any(
            op.status != "success"
            or op.request_hash != job.request_hash
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
    if attempt.outbox_id != intent.pk or attempt.status != "done":
        raise RevisionConflict()
    leads = calls = 0
    for op in operations:
        supplied = terminal_proofs[op.pk]
        if (
            type(supplied) is not tuple
            or len(supplied) != 2
            or not isinstance(supplied[0], bytes)
            or not isinstance(supplied[1], str)
        ):
            raise ValidationError("Current exact source-final proof is required.")
        batches = list(
            ResultBatch.objects.select_for_update()
            .filter(operation=op)
            .order_by("ordinal")[:1001]
        )
        accepted = list(
            BatchAcceptance.objects.select_for_update()
            .select_related("candidate")
            .filter(candidate__batch__operation=op)
        )
        by_batch = {item.candidate.batch_id: item for item in accepted}
        if (
            not 1 <= len(batches) <= min(1000, op.call_limit, reservation.leads)
            or len(accepted) != len(batches)
            or any(
                batch.ordinal != position or batch.pk not in by_batch
                for position, batch in enumerate(batches, 1)
            )
        ):
            raise RevisionConflict()
        for batch in batches:
            item = by_batch[batch.pk]
            if (
                item.source_code != op.source_code
                or item.candidate.source_code != op.source_code
                or item.candidate.candidate_count != item.accepted_count
                or AcceptedResult.objects.filter(
                    batch_acceptance=item, workspace_id=workspace_id, job=job
                ).count()
                != item.accepted_count
            ):
                raise RevisionConflict()
        binding = TerminalBinding(
            op.workspace_id,
            op.job_id,
            op.pk,
            op.provider_key,
            op.source_code,
            op.request_hash,
            op.policy_fingerprint,
            reservation.leads,
            op.call_limit,
            tuple(
                TerminalBatch(
                    batch.pk,
                    by_batch[batch.pk].body_hash,
                    by_batch[batch.pk].accepted_count,
                    by_batch[batch.pk].provider_calls,
                )
                for batch in batches
            ),
        )
        proof = verified_terminal_manifest(supplied[0], supplied[1], binding)
        final = SourceBatchTerminal.objects.select_for_update().filter(operation=op).first()
        if final is None:
            raise RevisionConflict()
        if (
            final.source_code,
            final.body_hash,
            final.batch_set_hash,
            final.batch_count,
            final.accepted_count,
            final.provider_calls,
            final.receipt_ref,
        ) != (
            op.source_code,
            proof.body_hash,
            proof.batch_set_hash,
            proof.batch_count,
            proof.accepted_count,
            proof.provider_calls,
            proof.receipt_ref,
        ):
            raise IdempotencyConflict()
        leads += proof.accepted_count
        calls += proof.provider_calls
    if (
        leads != job.result_count
        or leads > reservation.leads
        or calls > reservation.provider_calls
        or reservation.settlement
        != {"leads": leads, "jobs": 1, "provider_calls": calls, "exports": 0}
        or AcceptedResult.objects.filter(
            workspace_id=workspace_id, job=job, batch_acceptance__isnull=False
        ).count()
        != leads
    ):
        raise RevisionConflict()
    return job, False
