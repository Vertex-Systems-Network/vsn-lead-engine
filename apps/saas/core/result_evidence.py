"""Internal candidate preflight only: no result writes, dedupe or acceptance grant."""

import hashlib
import hmac
import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .candidate_records import ALLOWED_FIELDS as ALLOWED_FIELDS
from .candidate_records import RECORD as RECORD
from .candidate_records import RIGHTS as RIGHTS
from .candidate_records import CandidateReview as CandidateReview
from .candidate_records import checked_candidate_records
from .candidate_records import instant as instant
from .candidate_records import token as token
from .jobs import RevisionConflict, eligible_sources
from .models import DispatchOperation, DispatchReceipt, Entitlement, SourcePolicy, UsageReservation
from .receipts import unique_object
from .usage import lock_workspace

ENVELOPE = {
    "version",
    "key_id",
    "event_ref",
    "operation_id",
    "workspace_id",
    "job_id",
    "source_code",
    "provider_key",
    "request_hash",
    "policy_fingerprint",
    "issued_at",
    "records",
}


def checked_candidates(body, signature, operation, policy, search, now):
    """Strict separate v1 candidate envelope; v1 terminal receipts stay unchanged."""
    try:
        if not isinstance(body, bytes) or not 1 <= len(body) <= 131072:
            raise ValueError()
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise ValueError()
        data = json.loads(body, object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != ENVELOPE:
            raise ValueError()
        if (
            type(data["version"]) is not int
            or data["version"] != 1
            or not token(data["key_id"], 64)
        ):
            raise ValueError()
        secret = settings.SAAS_RESULT_VERIFIERS.get(operation.source_code, {}).get(data["key_id"])
        if (
            not isinstance(secret, bytes)
            or len(secret) < 32
            or not hmac.compare_digest(
                signature, hmac.new(secret, body, hashlib.sha256).hexdigest()
            )
        ):
            raise ValueError()
        for key, expected in {
            "operation_id": str(operation.id),
            "workspace_id": str(operation.workspace_id),
            "job_id": str(operation.job_id),
            "source_code": operation.source_code,
            "provider_key": str(operation.provider_key),
            "request_hash": operation.request_hash,
            "policy_fingerprint": operation.policy_fingerprint,
        }.items():
            if data[key] != expected:
                raise ValueError()
        issued = instant(data["issued_at"])
        if not token(data["event_ref"]) or not operation.created_at - timedelta(
            minutes=5
        ) <= issued <= now + timedelta(minutes=5):
            raise ValueError()
        return checked_candidate_records(body, data, policy, search, now, issued)
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        UnicodeError,
        AttributeError,
        OSError,
        RecursionError,
    ):
        raise ValidationError("Candidate evidence is unavailable or invalid.") from None


@transaction.atomic
def review_candidates(user, workspace_id, operation_id, body, signature):
    """Recheck current authority under locks; produce only redacted review metadata."""
    lock_workspace(user, workspace_id)
    operation = (
        DispatchOperation.objects.select_for_update()
        .select_related("job", "outbox", "attempt")
        .filter(pk=operation_id, workspace_id=workspace_id, job__workspace_id=workspace_id)
        .first()
    )
    if operation is None:
        raise Http404("Workspace resource not found.")
    job, intent = operation.job, operation.outbox
    if intent.result_protocol != 2:
        raise RevisionConflict()
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current or entitlement.lead_limit < 1:
        raise PermissionDenied("Workspace entitlement is inactive.")
    if (
        job.status != "running"
        or job.result_count != 0
        or intent.status != "started"
        or reservation.status != "reserved"
        or reservation.workspace_id != workspace_id
        or intent.job_id != job.id
        or operation.attempt.outbox_id != intent.id
        or operation.status not in {"started", "unknown"}
        or DispatchReceipt.objects.filter(operation=operation).exists()
    ):
        raise RevisionConflict()
    snapshot, _ = eligible_sources(job.search)
    expected = {"version": operation.policy_version, "hash": operation.policy_fingerprint}
    if (
        snapshot.get(operation.source_code) != expected
        or intent.source_snapshot.get(operation.source_code) != expected
        or operation.request_hash != job.request_hash
    ):
        raise RevisionConflict()
    policy = SourcePolicy.objects.get(pk=operation.source_code)
    review = checked_candidates(body, signature, operation, policy, job.search, timezone.now())
    if review.candidate_count > min(reservation.leads, entitlement.lead_limit):
        raise ValidationError("Candidate evidence exceeds its current bounded review capacity.")
    return review
