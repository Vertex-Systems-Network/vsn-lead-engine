"""Internal dual-attested single-source result intake. Registries default empty."""

import hashlib
import hmac
import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, eligible_sources
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    CandidateEvidence,
    DispatchOperation,
    DispatchReceipt,
    Entitlement,
    JobAttempt,
    ResultAcceptance,
    SourcePolicy,
    UsageCounter,
    UsageReservation,
)
from .receipts import unique_object
from .result_evidence import checked_candidates, instant, token
from .services import IdempotencyConflict, membership_for
from .usage import COUNTERS, _settle_locked, lock_workspace

FIELDS = {
    "version",
    "kind",
    "key_id",
    "dedupe_key_id",
    "receipt_ref",
    "workspace_id",
    "job_id",
    "operation_id",
    "provider_key",
    "request_hash",
    "policy_fingerprint",
    "source_code",
    "candidate_event_ref",
    "candidate_body_hash",
    "registry_namespace",
    "registry_contract",
    "qualification_contract",
    "registry_state",
    "issued_at",
    "provider_calls",
    "records",
}


def verified_acceptance(
    body, signature, dedupe_signature, operation, candidate, candidate_body, now
):
    """Two independent exact-byte attestations; no claimed count/uniqueness from browsers.

    The trusted isolated R2 signer must attest canonical engine qualification and
    committed fingerprints for this exact candidate digest. This verifier does not
    call R2, implement an alternative fingerprint algorithm or prove a real signer
    integration. No keys are configured and no HTTP intake is exposed by default.
    """
    try:
        if not isinstance(body, bytes) or not 1 <= len(body) <= 16384:
            raise ValueError()
        data = json.loads(body, object_pairs_hook=unique_object)
        if (
            not isinstance(data, dict)
            or set(data) != FIELDS
            or type(data["version"]) is not int
            or data["version"] != 2
        ):
            raise ValueError()
        namespace = f"saas-results/v1/{operation.workspace_id}"
        for key, expected in {
            "kind": "accepted-results",
            "workspace_id": str(operation.workspace_id),
            "job_id": str(operation.job_id),
            "operation_id": str(operation.id),
            "provider_key": str(operation.provider_key),
            "request_hash": operation.request_hash,
            "policy_fingerprint": operation.policy_fingerprint,
            "source_code": operation.source_code,
            "candidate_event_ref": candidate.event_ref,
            "candidate_body_hash": candidate.body_hash,
            "registry_namespace": namespace,
            "registry_contract": "r2-exact-objects-v1",
            "qualification_contract": "vsn-phone-usca-v1",
            "registry_state": "committed",
        }.items():
            if data[key] != expected:
                raise ValueError()
        if (
            not token(data["key_id"], 64)
            or not token(data["dedupe_key_id"], 64)
            or not token(data["receipt_ref"])
        ):
            raise ValueError()
        source_key = settings.SAAS_ACCEPTANCE_VERIFIERS.get(operation.source_code, {}).get(
            data["key_id"]
        )
        dedupe_key = settings.SAAS_DEDUPE_VERIFIERS.get(namespace, {}).get(data["dedupe_key_id"])
        if source_key == dedupe_key:
            raise ValueError()
        candidate_data = json.loads(candidate_body, object_pairs_hook=unique_object)
        candidate_key = settings.SAAS_RESULT_VERIFIERS.get(operation.source_code, {}).get(
            candidate_data["key_id"]
        )
        if dedupe_key == candidate_key:
            raise ValueError()
        for key, sig in [(source_key, signature), (dedupe_key, dedupe_signature)]:
            if (
                not isinstance(key, bytes)
                or len(key) < 32
                or not isinstance(sig, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sig)
                or not hmac.compare_digest(sig, hmac.new(key, body, hashlib.sha256).hexdigest())
            ):
                raise ValueError()
        issued = instant(data["issued_at"])
        if not candidate.recorded_at - timedelta(minutes=5) <= issued <= now + timedelta(minutes=5):
            raise ValueError()
        calls = data["provider_calls"]
        if type(calls) is not int or not 1 <= calls <= operation.call_limit:
            raise ValueError()
        rows = data["records"]
        if not isinstance(rows, list) or len(rows) != candidate.candidate_count:
            raise ValueError()
        expected_records = {row["record_ref"]: row for row in candidate_data["records"]}
        expected_refs = set(expected_records)
        refs, all_tokens = set(), set()
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) != {"record_ref", "tokens"}
                or not token(row["record_ref"])
                or row["record_ref"] in refs
            ):
                raise ValueError()
            refs.add(row["record_ref"])
            tokens = row["tokens"]
            if (
                not isinstance(tokens, list)
                or not 3 <= len(tokens) <= 4
                or any(
                    not isinstance(t, str) or not re.fullmatch(r"[sdnl]:[0-9a-f]{24}", t)
                    for t in tokens
                )
            ):
                raise ValueError()
            if (
                len(tokens) != len(set(tokens))
                or len({t[0] for t in tokens}) != len(tokens)
                or {t[0] for t in tokens}
                != (
                    {"s", "n", "l", "d"}
                    if expected_records.get(row["record_ref"], {}).get("fields", {}).get("website")
                    else {"s", "n", "l"}
                )
                or all_tokens.intersection(tokens)
            ):
                raise ValueError()
            all_tokens.update(tokens)
        if refs != expected_refs:
            raise ValueError()
        return data, hashlib.sha256(body).hexdigest()
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
        raise ValidationError("Accepted-result evidence is unavailable or invalid.") from None


@transaction.atomic
def accept_results(
    user,
    workspace_id,
    operation_id,
    candidate_body,
    candidate_signature,
    body,
    signature,
    dedupe_signature,
):
    """Store/finalize one entire bounded single-source batch, atomically and once."""
    lock_workspace(user, workspace_id)
    if membership_for(user, workspace_id, lock=True).role not in {"owner", "admin"}:
        raise PermissionDenied("Only current administrators can reconcile accepted results.")
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
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    if (
        intent.job_id != job.id
        or operation.attempt.outbox_id != intent.id
        or reservation.workspace_id != workspace_id
        or operation.request_hash != job.request_hash
    ):
        raise RevisionConflict()
    snapshot, _ = eligible_sources(job.search)
    expected = {"version": operation.policy_version, "hash": operation.policy_fingerprint}
    if (
        snapshot.get(operation.source_code) != expected
        or intent.source_snapshot != {operation.source_code: expected}
        or DispatchOperation.objects.filter(outbox=intent).count() != 1
    ):
        raise RevisionConflict()
    policy = SourcePolicy.objects.get(pk=operation.source_code)
    now = timezone.now()
    review = checked_candidates(
        candidate_body, candidate_signature, operation, policy, job.search, now
    )
    candidate = (
        CandidateEvidence.objects.select_for_update()
        .filter(
            operation=operation,
            source_code=operation.source_code,
            body_hash=review.body_hash,
            event_ref=review.event_ref,
        )
        .first()
    )
    if (
        candidate is None
        or candidate.candidate_count != review.candidate_count
        or candidate.earliest_delete_at != review.earliest_delete_at
    ):
        raise ValidationError("Recorded candidate evidence is unavailable or changed.")
    data, digest = verified_acceptance(
        body, signature, dedupe_signature, operation, candidate, candidate_body, now
    )
    previous = ResultAcceptance.objects.filter(operation=operation).first()
    if previous is not None:
        if previous.body_hash != digest:
            raise IdempotencyConflict()
        return previous, False
    if (
        job.status != "running"
        or job.result_count != 0
        or job.revision >= 2147483647
        or intent.status != "started"
        or operation.status not in {"started", "unknown"}
        or operation.attempt.status != "started"
        or reservation.status != "reserved"
        or DispatchReceipt.objects.filter(operation=operation).exists()
    ):
        raise RevisionConflict()
    if (
        review.candidate_count > reservation.leads
        or data["provider_calls"] > reservation.provider_calls
        or reservation.jobs < 1
    ):
        raise ValidationError("Actual accepted use exceeds reserved capacity.")
    counter = UsageCounter.objects.select_for_update().get(workspace_id=workspace_id)
    reserved = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    if any(
        getattr(counter, name) + (reserved[name] or 0) > getattr(entitlement, limit)
        for name, limit in COUNTERS.items()
    ):
        raise PermissionDenied("Current workspace limits cannot cover its reserved use.")
    records = json.loads(candidate_body, object_pairs_hook=unique_object)["records"]
    token_rows = {row["record_ref"]: row["tokens"] for row in data["records"]}
    try:
        with transaction.atomic():
            acceptance = ResultAcceptance.objects.create(
                operation=operation,
                candidate=candidate,
                receipt_ref=data["receipt_ref"],
                source_code=operation.source_code,
                source_key_id=data["key_id"],
                dedupe_key_id=data["dedupe_key_id"],
                body_hash=digest,
                namespace=data["registry_namespace"],
                accepted_count=len(records),
                provider_calls=data["provider_calls"],
            )
            for row in records:
                result = AcceptedResult.objects.create(
                    workspace_id=workspace_id,
                    job=job,
                    acceptance=acceptance,
                    record_ref=row["record_ref"],
                    country=row["country"],
                    category=row["category"],
                    fields=row["fields"],
                    field_lineage=row["field_lineage"],
                    observed_at=instant(row["observed_at"]),
                    delete_at=instant(row["observed_at"])
                    + timedelta(seconds=policy.controls["result_contract"]["max_age_seconds"]),
                    purpose=row["purpose"],
                    retention_version=row["retention_version"],
                )
                AcceptedFingerprint.objects.bulk_create(
                    [
                        AcceptedFingerprint(workspace_id=workspace_id, result=result, token=t)
                        for t in token_rows[row["record_ref"]]
                    ]
                )
            _settle_locked(
                reservation,
                {"leads": len(records), "jobs": 1, "provider_calls": data["provider_calls"]},
            )
            operation.status = "success"
            operation.save(update_fields=["status"])
            intent.status = "done"
            intent.save(update_fields=["status", "updated_at"])
            JobAttempt.objects.filter(pk=operation.attempt_id, status="started").update(
                status="done"
            )
            job.status, job.result_count = "completed", len(records)
            job.revision += 1
            job.save(update_fields=["status", "result_count", "revision", "updated_at"])
            if review.earliest_delete_at <= timezone.now():
                raise ValidationError("Candidate eligibility expired before finalization.")
    except IntegrityError:
        raise IdempotencyConflict() from None
    return acceptance, True
