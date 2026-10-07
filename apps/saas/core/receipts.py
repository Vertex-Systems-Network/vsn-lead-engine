"""Evidence-bound internal reconciliation. No endpoint, provider or sender enabled."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict
from .models import (
    DispatchOperation,
    DispatchReceipt,
    Job,
    JobAttempt,
    JobOutbox,
    UsageReservation,
    Workspace,
)
from .services import IdempotencyConflict, membership_for
from .usage import _release_locked, _settle_locked

FIELDS = {
    "version",
    "key_id",
    "receipt_ref",
    "operation_id",
    "workspace_id",
    "job_id",
    "source_code",
    "provider_key",
    "request_hash",
    "policy_fingerprint",
    "outcome",
    "provider_calls",
    "issued_at",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def verified_receipt(body, signature, operation):
    """Exact-byte HMAC contract only; no actual provider supports it by default."""
    try:
        if not isinstance(body, bytes) or not 1 <= len(body) <= 8192:
            raise ValueError()
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise ValueError()
        data = json.loads(body, object_pairs_hook=unique_object)
        if (
            not isinstance(data, dict)
            or set(data) != FIELDS
            or type(data["version"]) is not int
            or data["version"] != 1
        ):
            raise ValueError()
        if not isinstance(data["key_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,64}", data["key_id"]
        ):
            raise ValueError()
        secret = settings.SAAS_RECEIPT_VERIFIERS.get(operation.source_code, {}).get(data["key_id"])
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
        if not isinstance(data["receipt_ref"], str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,96}", data["receipt_ref"]
        ):
            raise ValueError()
        calls = data["provider_calls"]
        if (
            type(calls) is not int
            or not 0 <= calls <= 2147483647
            or data["outcome"] not in {"success", "noeffect"}
        ):
            raise ValueError()
        if (data["outcome"] == "noeffect" and calls != 0) or (
            data["outcome"] == "success" and calls < 1
        ):
            raise ValueError()
        if type(data["issued_at"]) is not int:
            raise ValueError()
        issued_at = datetime.fromtimestamp(data["issued_at"], UTC)
        if issued_at < operation.created_at - timedelta(
            minutes=5
        ) or issued_at > timezone.now() + timedelta(minutes=5):
            raise ValueError()
        return data, issued_at, hashlib.sha256(body).hexdigest()
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError, AttributeError, OSError):
        raise ValidationError("Receipt evidence is unavailable or invalid.") from None


@transaction.atomic
def reconcile_receipt(user, workspace_id, operation_id, body, signature):
    membership = membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership = membership_for(user, workspace_id, lock=True)
    if membership.role not in {"owner", "admin"}:
        raise PermissionDenied("Only current workspace administrators can reconcile evidence.")
    operation = DispatchOperation.objects.filter(
        pk=operation_id, workspace_id=workspace_id, job__workspace_id=workspace_id
    ).first()
    if operation is None:
        raise Http404("Workspace resource not found.")
    job = Job.objects.select_for_update().get(pk=operation.job_id, workspace_id=workspace_id)
    intent = JobOutbox.objects.select_for_update().get(pk=operation.outbox_id, job=job)
    reservation = UsageReservation.objects.select_for_update().get(
        pk=intent.reservation_id, workspace_id=workspace_id
    )
    operation = DispatchOperation.objects.select_for_update().get(
        pk=operation.id, attempt__outbox=intent
    )
    data, issued_at, digest = verified_receipt(body, signature, operation)
    previous = DispatchReceipt.objects.filter(operation=operation).first()
    if previous:
        if previous.body_hash != digest:
            raise IdempotencyConflict()
        return previous
    if (
        intent.status != "started"
        or job.status != "running"
        or reservation.status != "reserved"
        or operation.status not in {"started", "unknown"}
        or job.revision >= 2147483647
        or job.result_count != 0
        or operation.call_limit < 1
    ):
        raise RevisionConflict()
    # Source-event collisions cannot be repurposed for another operation/tenant.
    if DispatchReceipt.objects.filter(
        source_code=operation.source_code, receipt_ref=data["receipt_ref"]
    ).exists():
        raise IdempotencyConflict()
    rows = list(DispatchOperation.objects.filter(outbox=intent).order_by("source_code"))
    if (
        not 1 <= len(rows) <= 12
        or {r.source_code for r in rows} != set(intent.source_snapshot)
        or any(r.workspace_id != workspace_id or r.job_id != job.id for r in rows)
    ):
        raise RevisionConflict()
    if data["provider_calls"] > operation.call_limit:
        raise ValidationError("Recorded source use exceeds its saved operation budget.")
    existing = list(DispatchReceipt.objects.filter(operation__outbox=intent))
    if (
        sum(r.provider_calls for r in existing) + data["provider_calls"]
        > reservation.provider_calls
    ):
        raise ValidationError("Recorded provider use exceeds the reserved budget.")
    try:
        with transaction.atomic():
            receipt = DispatchReceipt.objects.create(
                operation=operation,
                source_code=operation.source_code,
                receipt_ref=data["receipt_ref"],
                key_id=data["key_id"],
                body_hash=digest,
                outcome=data["outcome"],
                provider_calls=data["provider_calls"],
                issued_at=issued_at,
            )
    except IntegrityError:
        raise IdempotencyConflict() from None
    operation.status = receipt.outcome
    operation.save(update_fields=["status"])
    if len(existing) + 1 == len(rows):
        completed = existing + [receipt]
        success = any(r.outcome == "success" for r in completed)
        # No accepted-lead storage/qualification exists yet. Receipts cannot mint
        # leads/exports or increase result_count. Future adapters require that gate.
        if success:
            _settle_locked(
                reservation, {"jobs": 1, "provider_calls": sum(r.provider_calls for r in completed)}
            )
        else:
            _release_locked(reservation)
        intent.status = "done"
        intent.save(update_fields=["status", "updated_at"])
        JobAttempt.objects.filter(outbox=intent, status="started").update(status="done")
        job.status = "completed" if success else "failed"
        job.revision += 1
        job.save(update_fields=["status", "revision", "updated_at"])
    return receipt
