"""Internal candidate preflight only: no result writes, dedupe or acceptance grant."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

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
RECORD = {
    "record_ref",
    "country",
    "category",
    "observed_at",
    "fields",
    "field_lineage",
    "purpose",
    "retention_version",
}
RIGHTS = {
    "version",
    "purpose",
    "retention_version",
    "max_age_seconds",
    "display_fields",
    "storage_fields",
    "display_allowed",
    "storage_allowed",
}
ALLOWED_FIELDS = {"business_name", "phone", "city", "website", "status", "address"}


@dataclass(frozen=True, slots=True)
class CandidateReview:
    """Redacted comparison evidence, explicitly not an accepted-result receipt.

    Equal bytes have equal digests; durable event collision/replay and R2 dedupe
    remain future ingestion gates. Never use this count to settle usage.
    """

    event_ref: str
    body_hash: str
    candidate_count: int
    earliest_delete_at: datetime


def token(value, limit=96):
    return isinstance(value, str) and re.fullmatch(rf"[A-Za-z0-9._:-]{{1,{limit}}}", value)


def instant(value):
    if type(value) is not int:
        raise ValueError()
    return datetime.fromtimestamp(value, UTC)


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
        rights = policy.controls.get("result_contract")
        if not isinstance(rights, dict) or set(rights) != RIGHTS:
            raise ValueError()
        if type(rights["version"]) is not int or rights["version"] != 1:
            raise ValueError()
        if rights["display_allowed"] is not True or rights["storage_allowed"] is not True:
            raise ValueError()
        if not token(rights["purpose"], 64) or not token(rights["retention_version"], 64):
            raise ValueError()
        age = rights["max_age_seconds"]
        if type(age) is not int or not 1 <= age <= 2592000:
            raise ValueError()
        for key in ("display_fields", "storage_fields"):
            values = rights[key]
            if (
                not isinstance(values, list)
                or not values
                or any(type(x) is not str for x in values)
                or len(values) != len(set(values))
                or not set(values) <= ALLOWED_FIELDS
            ):
                raise ValueError()
        rows = data["records"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= min(25, search["result_limit"]):
            raise ValueError()
        refs = set()
        deadlines = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != RECORD or not token(row["record_ref"]):
                raise ValueError()
            if row["record_ref"] in refs:
                raise ValueError()
            refs.add(row["record_ref"])
            if (
                row["country"] not in {"US", "CA"}
                or row["country"] not in search["countries"]
                or row["category"] not in search["categories"]
            ):
                raise ValueError()
            if (
                row["purpose"] != rights["purpose"]
                or row["retention_version"] != rights["retention_version"]
            ):
                raise ValueError()
            observed = instant(row["observed_at"])
            if (
                observed > min(issued, now) + timedelta(minutes=5)
                or observed + timedelta(seconds=age) <= now
            ):
                raise ValueError()
            fields = row["fields"]
            if (
                not isinstance(fields, dict)
                or not {"business_name", "phone"} <= set(fields)
                or not set(fields) <= ALLOWED_FIELDS
            ):
                raise ValueError()
            required = {
                "business_name" if field == "name" else field for field in search["required_fields"]
            }
            if not required <= set(fields):
                raise ValueError()
            if not set(fields) <= set(rights["display_fields"]) & set(rights["storage_fields"]):
                raise ValueError()
            if any(
                not isinstance(v, str)
                or not v.strip()
                or len(v) > 2000
                or any(ord(c) < 32 or ord(c) == 127 for c in v)
                for v in fields.values()
            ):
                raise ValueError()
            # Conservative normalized NANP syntax. Not reachability/geographic proof.
            if not re.fullmatch(r"\+1[2-9][0-9]{2}[2-9][0-9]{6}", fields["phone"]):
                raise ValueError()
            if search["statuses"] and fields.get("status") not in search["statuses"]:
                raise ValueError()
            lineage = row["field_lineage"]
            if (
                not isinstance(lineage, dict)
                or set(lineage) != set(fields)
                or any(v != row["record_ref"] for v in lineage.values())
            ):
                raise ValueError()
            deadlines.append(observed + timedelta(seconds=age))
        return CandidateReview(
            data["event_ref"], hashlib.sha256(body).hexdigest(), len(rows), min(deadlines)
        )
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
