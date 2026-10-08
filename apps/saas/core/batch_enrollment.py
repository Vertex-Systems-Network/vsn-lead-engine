"""Disabled trusted-local protocol selection, never dispatch or intake permission."""

from django.conf import settings
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from .attempts import preflight
from .jobs import RevisionConflict, revision
from .models import Job, JobAttempt, JobOutbox, User, Workspace
from .services import membership_for


@transaction.atomic
def enroll_batch_protocol(user, workspace_id, job_id, expected_revision):
    """Select v3 only before any attempt; existing v2 evidence cannot be reclassified."""
    if settings.SAAS_BATCH_ENROLLMENT_ENABLED is not True:
        raise PermissionDenied("Batch enrollment is unavailable.")
    expected_revision = revision(expected_revision)
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    actor = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
    if actor is None or membership_for(actor, workspace_id, lock=True).role not in {
        "owner",
        "admin",
    }:
        raise PermissionDenied("Only current administrators can enroll batch jobs.")
    job = Job.objects.select_for_update().filter(pk=job_id, workspace_id=workspace_id).first()
    if job is None:
        raise Http404("Workspace resource not found.")
    intent = (
        JobOutbox.objects.select_for_update()
        .select_related("job", "submitted_by")
        .filter(job=job)
        .first()
    )
    if intent is None or job.revision != expected_revision or job.result_count != 0:
        raise RevisionConflict()
    if JobAttempt.objects.filter(outbox=intent).exists() or intent.operations.exists():
        raise RevisionConflict()
    allowed = settings.SAAS_BATCH_ENROLLMENT_SOURCES
    if type(allowed) not in (set, frozenset) or not set(intent.source_snapshot).issubset(allowed):
        raise PermissionDenied("Batch source capability is unavailable.")
    # Same source/cap/period/normalized request/deadline checks as ordinary dispatch.
    # Enrollment is the only caller allowed past the v3 quarantine guard.
    preflight(intent, allow_batch_enrollment=True)
    if intent.result_protocol not in (2, 3):
        raise RevisionConflict()
    created = intent.result_protocol == 2
    if created:
        intent.result_protocol = 3
        intent.save(update_fields=["result_protocol", "updated_at"])
    return intent, created
