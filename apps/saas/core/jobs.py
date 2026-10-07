"""Atomic internal pre-dispatch intents. No worker/provider/customer submit API."""

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from .models import Job, JobAttempt, JobOutbox, SourcePolicy
from .serializers import SearchSerializer
from .usage import lock_workspace, release_usage, reserve_usage

EVIDENCE = {"collection", "storage", "display", "export", "territory", "fields", "cost"}
CONTROLS = {"attribution", "retention_deletion", "rate_limit", "freshness", "failure_behavior"}


class RevisionConflict(APIException):
    status_code = 409
    default_detail = "Job state or revision changed. Refresh the job."
    default_code = "revision_conflict"


def revision(value):
    if type(value) is not int or value < 0 or value > 2147483646:
        raise ValidationError("A bounded nonnegative expected revision is required.")
    return value


def nonempty_mapping(value, required):
    return isinstance(value, dict) and all(
        isinstance(value.get(key), str) and value[key].strip() for key in required
    )


def eligible_sources(search):
    codes = search["source_codes"]
    if not codes:
        raise ValidationError("Choose explicitly eligible sources before enqueue.")
    policies = list(
        SourcePolicy.objects.select_for_update().filter(code__in=codes).order_by("code")
    )
    if len(policies) != len(codes):
        raise PermissionDenied("Requested source policy is unavailable.")
    snapshot = {}
    calls = 0
    for policy in policies:
        allowed = {
            "countries": policy.countries,
            "categories": policy.categories,
            "statuses": policy.statuses,
            "required_fields": policy.fields,
        }
        if (
            not policy.enabled
            or not policy.free_collection
            or policy.version < 1
            or not nonempty_mapping(policy.evidence, EVIDENCE)
            or not nonempty_mapping(policy.controls, CONTROLS)
            or policy.max_provider_calls < 1
            or policy.max_provider_calls > 2147483647
        ):
            raise PermissionDenied("Source rights, controls or free cost evidence is unavailable.")
        for key, supported in allowed.items():
            if not isinstance(supported, list) or not all(isinstance(x, str) for x in supported):
                raise PermissionDenied("Source capability metadata is unavailable.")
            if not set(search[key]).issubset(supported):
                raise PermissionDenied("Requested scope exceeds source policy.")
        data = {
            "version": policy.version,
            "capabilities": allowed,
            "evidence": policy.evidence,
            "controls": policy.controls,
            "max_provider_calls": policy.max_provider_calls,
            "free_collection": policy.free_collection,
        }
        snapshot[policy.code] = {
            "version": policy.version,
            "hash": hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        calls += policy.max_provider_calls
    if calls > 2147483647:
        raise ValidationError("Provider call budget exceeds supported bounds.")
    return snapshot, calls


def locked_job(user, workspace_id, job_id):
    lock_workspace(user, workspace_id)
    job = Job.objects.select_for_update().filter(workspace_id=workspace_id, id=job_id).first()
    if job is None:
        raise Http404("Workspace resource not found.")
    return job


@transaction.atomic
def enqueue_job(user, workspace_id, job_id, expected_revision):
    """Persist job+budget+intent together; source activation stays internal."""
    expected_revision = revision(expected_revision)
    job = locked_job(user, workspace_id, job_id)
    existing = JobOutbox.objects.filter(job=job).first()
    if existing:
        if (
            job.status != "queued"
            or existing.status != "pending"
            or existing.submitted_revision != expected_revision
        ):
            raise RevisionConflict()
        if existing.reservation.status != "reserved":
            raise RevisionConflict()
        return job, False
    if job.status != "draft" or job.revision != expected_revision:
        raise RevisionConflict()
    serializer = SearchSerializer(data=job.search)
    serializer.is_valid(raise_exception=True)
    search = serializer.validated_data
    if search != job.search:
        raise ValidationError("Stored draft must contain a normalized validated search.")
    snapshot, calls = eligible_sources(search)
    reservation = reserve_usage(
        user,
        workspace_id,
        f"job:{job.id}",
        {"leads": search["result_limit"], "jobs": 1, "provider_calls": calls},
    )
    if reservation.status != "reserved":
        raise RevisionConflict()
    JobOutbox.objects.create(
        job=job,
        submitted_by=user,
        reservation=reservation,
        submitted_revision=expected_revision,
        source_snapshot=snapshot,
        expires_at=timezone.now() + timedelta(days=1),
    )
    job.status = "queued"
    job.revision += 1
    job.save(update_fields=["status", "revision", "updated_at"])
    return job, True


@transaction.atomic
def cancel_pending_job(user, workspace_id, job_id, expected_revision):
    """Only draft or queued cancellation; running-work semantics remain unavailable."""
    expected_revision = revision(expected_revision)
    job = locked_job(user, workspace_id, job_id)
    if job.status == "cancelled" and job.revision == expected_revision + 1:
        return job
    if job.status not in {"draft", "queued"} or job.revision != expected_revision:
        raise RevisionConflict()
    outbox = JobOutbox.objects.select_for_update().filter(job=job).first()
    if job.status == "queued":
        if outbox is None or outbox.status != "pending":
            raise RevisionConflict()
        release_usage(user, workspace_id, outbox.reservation_id)
        JobAttempt.objects.filter(outbox=outbox, status="leased").update(status="cancelled")
        outbox.status = "cancelled"
        outbox.save(update_fields=["status", "updated_at"])
    job.status = "cancelled"
    job.revision += 1
    job.save(update_fields=["status", "revision", "updated_at"])
    return job
