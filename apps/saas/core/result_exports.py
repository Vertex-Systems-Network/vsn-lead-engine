"""Bounded source-aware CSV preparation/accounting. No persisted download copy."""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import PermissionDenied, ValidationError

from vsn_lead_engine.saas.contracts import Entitlement as ExportEntitlement
from vsn_lead_engine.saas.contracts import ExportSpec
from vsn_lead_engine.saas.source_policy import (
    SearchAuthorizationError,
    authorize_export,
)
from vsn_lead_engine.saas.source_policy import (
    SourcePolicy as ExportPolicy,
)

from .models import AcceptedResult, Entitlement, ResultExport, SourcePolicy
from .periods import active_window
from .result_evidence import ALLOWED_FIELDS
from .result_query import results_snapshot
from .services import IdempotencyConflict
from .usage import _settle_locked, lock_workspace, reserve_usage

FIELD_ORDER = ("business_name", "phone", "city", "website", "status", "address")
EXPORT_RIGHTS = {"version", "allowed", "fields", "purpose", "retention_version", "attribution"}


@dataclass(frozen=True)
class PreparedExport:
    receipt_id: UUID
    csv_bytes: bytes
    record_count: int
    delete_at: datetime
    created: bool


def specification(data):
    if not isinstance(data, dict) or set(data) != {"result_ids", "fields"}:
        raise ValidationError("Choose explicit bounded result IDs and fields.")
    ids, fields = data["result_ids"], data["fields"]
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 25
        or any(type(x) is not str or len(x) != 36 for x in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(fields, list)
        or not 1 <= len(fields) <= 6
        or any(type(x) is not str for x in fields)
        or len(set(fields)) != len(fields)
        or not set(fields) <= ALLOWED_FIELDS
    ):
        raise ValidationError("Export selection exceeds supported bounds.")
    try:
        normalized = sorted(str(UUID(x)) for x in ids)
    except ValueError:
        raise ValidationError("Choose valid result IDs.") from None
    if len(set(normalized)) != len(normalized):
        raise ValidationError("Duplicate result IDs are unavailable.")
    return normalized, [f for f in FIELD_ORDER if f in fields]


def csv_cell(value):
    # QUOTE_ALL protects CSV structure; the apostrophe prevents spreadsheet formulas,
    # including E.164 +phone numbers and whitespace-prefixed formula-like strings.
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_rights(policy):
    rights = policy.controls.get("export_contract")
    stored = policy.controls["result_contract"]
    if (
        not isinstance(rights, dict)
        or set(rights) != EXPORT_RIGHTS
        or type(rights["version"]) is not int
        or rights["version"] != 1
        or rights["allowed"] is not True
        or not isinstance(rights["fields"], list)
        or not rights["fields"]
        or any(type(x) is not str for x in rights["fields"])
        or not set(rights["fields"]) <= ALLOWED_FIELDS
        or rights["purpose"] != stored["purpose"]
        or rights["retention_version"] != stored["retention_version"]
        or type(rights["attribution"]) is not str
        or not rights["attribution"].strip()
        or len(rights["attribution"]) > 240
        or any(ord(c) < 32 or ord(c) == 127 for c in rights["attribution"])
    ):
        raise PermissionDenied("Source export rights are unavailable.")
    return rights


@transaction.atomic
def prepare_export(user, workspace_id, job_id, key, data):
    lock_workspace(user, workspace_id)
    if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValidationError("A bounded export idempotency key is required.")
    ids, fields = specification(data)
    request_hash = hashlib.sha256(
        json.dumps({"job_id": str(job_id), "ids": ids, "fields": fields}, sort_keys=True).encode()
    ).hexdigest()
    previous = ResultExport.objects.filter(workspace_id=workspace_id, key=key).first()
    if previous and (
        previous.created_by_id != user.id
        or previous.job_id != job_id
        or previous.request_hash != request_hash
    ):
        raise IdempotencyConflict()
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current or entitlement.export_limit < 1:
        raise PermissionDenied("Export entitlement is unavailable.")
    snapshot = results_snapshot(user, workspace_id, job_id)
    available = {r["id"]: r for r in snapshot["results"]}
    if not set(ids) <= set(available):
        raise PermissionDenied("Selected results are unavailable for export.")
    rows = [available[i] for i in ids]
    codes = {row["source_code"] for row in rows}
    policies = {}
    attribution = {}
    for code in sorted(codes):
        policy = SourcePolicy.objects.select_for_update().get(pk=code)
        rights = export_rights(policy)
        policies[code] = ExportPolicy(
            code=code,
            countries=frozenset(policy.countries),
            allowed_export_fields=frozenset(rights["fields"]),
            export_allowed=True,
            enabled=policy.enabled,
        )
        attribution[code] = rights["attribution"]
    try:
        authorize_export(
            ExportSpec(workspace_id, tuple(sorted(codes)), tuple(fields)),
            ExportEntitlement(
                workspace_id=workspace_id,
                plan_code="internal",
                source_codes=frozenset(policies),
                active=entitlement.is_current,
                export_enabled=entitlement.export_limit > 0,
            ),
            policies,
        )
    except (SearchAuthorizationError, ValueError):
        raise PermissionDenied("Selected export fields are unavailable.") from None
    if any(not set(fields) <= set(row["fields"]) for row in rows):
        raise PermissionDenied("Selected fields are unavailable on every selected result.")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(
        [
            *fields,
            "source",
            "policy_version",
            "observed_at",
            "delete_at",
            "retention_version",
            "attribution",
        ]
    )
    for row in rows:
        writer.writerow(
            [csv_cell(row["fields"][f]) for f in fields]
            + [
                csv_cell(row["source_code"]),
                str(row["policy_version"]),
                row["observed_at"],
                row["delete_at"],
                csv_cell(row["retention_version"]),
                csv_cell(attribution[row["source_code"]]),
            ]
        )
    content = stream.getvalue().encode("utf-8")
    if len(content) > 128 * 1024:
        raise ValidationError("Export exceeds supported output bounds.")
    digest = salted_hmac("saas.result-export.csv.v1", content, algorithm="sha256").hexdigest()
    delete_at = min(
        r.delete_at
        for r in AcceptedResult.objects.filter(workspace_id=workspace_id, job_id=job_id, id__in=ids)
    )
    if delete_at <= timezone.now():
        raise PermissionDenied("Selected results expired during export.")
    if previous:
        if previous.delete_at <= timezone.now() or previous.content_digest != digest:
            raise IdempotencyConflict()
        if previous.reservation.status != "settled":
            raise IdempotencyConflict()
        return PreparedExport(previous.id, content, len(rows), previous.delete_at, False)
    receipt_id = uuid4()
    # One export unit means one bounded prepared CSV, not HTTP delivery acknowledgement.
    reservation = reserve_usage(user, workspace_id, f"export:{receipt_id}", {"exports": 1})
    active_window(reservation.workspace.usagecounter, reservation)
    _settle_locked(reservation, {"exports": 1})
    receipt = ResultExport.objects.create(
        id=receipt_id,
        workspace_id=workspace_id,
        job_id=job_id,
        created_by=user,
        reservation=reservation,
        key=key,
        request_hash=request_hash,
        content_digest=digest,
        record_count=len(rows),
        delete_at=delete_at,
    )
    if delete_at <= timezone.now():
        raise PermissionDenied("Selected results expired during export.")
    return PreparedExport(receipt.id, content, len(rows), delete_at, True)
