"""Internal write-ahead boundary. No provider execution, retry or settlement."""

from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.utils import timezone

from .attempts import check_pre_dispatch
from .jobs import RevisionConflict
from .models import DispatchOperation, Job, JobOutbox, Workspace
from .services import membership_for
from .usage import lock_workspace


@transaction.atomic
def begin_dispatch(outbox_id, token):
    """Commit possible-effect identity before any future external I/O.

    This creates ledger state only; callers must not treat the returned rows as
    permission to send. No adapter/consumer is enabled and repeated begins conflict.
    """
    intent = JobOutbox.objects.select_related("job").get(pk=outbox_id)
    Workspace.objects.select_for_update().get(pk=intent.job.workspace_id)
    job = Job.objects.select_for_update().get(pk=intent.job_id)
    intent = JobOutbox.objects.select_for_update().get(pk=outbox_id)
    attempt = check_pre_dispatch(outbox_id, token)
    if job.revision >= 2147483647 or DispatchOperation.objects.filter(outbox=intent).exists():
        raise RevisionConflict()
    operations = [
        DispatchOperation.objects.create(
            workspace_id=job.workspace_id,
            job=job,
            outbox=intent,
            attempt=attempt,
            source_code=code,
            request_hash=job.request_hash,
            policy_version=policy["version"],
            policy_fingerprint=policy["hash"],
        )
        for code, policy in sorted(intent.source_snapshot.items())
    ]
    # Even time spent writing the ledger must not cross a lease/intent deadline.
    now = timezone.now()
    if (
        not operations
        or attempt.expires_at <= now
        or (intent.expires_at is not None and intent.expires_at <= now)
    ):
        raise RevisionConflict()
    attempt.status = "started"
    attempt.save(update_fields=["status"])
    intent.status = "started"
    intent.save(update_fields=["status", "updated_at"])
    job.status = "running"
    job.revision += 1
    job.save(update_fields=["status", "revision", "updated_at"])
    return operations


@transaction.atomic
def mark_outcome_unknown(user, workspace_id, operation_id):
    """Authorized internal review only: preserve reservation; never refund/retry."""
    lock_workspace(user, workspace_id)
    operation = (
        DispatchOperation.objects.select_for_update()
        .filter(
            workspace_id=workspace_id,
            pk=operation_id,
            job__workspace_id=workspace_id,
            outbox__job_id=F("job_id"),
            attempt__outbox_id=F("outbox_id"),
        )
        .first()
    )
    if operation is None:
        raise Http404("Workspace resource not found.")
    if operation.status == "started":
        operation.status = "unknown"
        operation.unknown_at = timezone.now()
        operation.save(update_fields=["status", "unknown_at"])
    return operation


@transaction.atomic
def dispatch_snapshot(user, workspace_id, outbox_id):
    """Stable redacted identities for review; not an outbound authorization."""
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership_for(user, workspace_id, lock=True)
    intent = JobOutbox.objects.filter(pk=outbox_id, job__workspace_id=workspace_id).first()
    if intent is None:
        raise Http404("Workspace resource not found.")
    return list(
        DispatchOperation.objects.filter(
            outbox=intent, workspace_id=workspace_id, job_id=intent.job_id
        ).order_by("source_code")[:12]
    )
