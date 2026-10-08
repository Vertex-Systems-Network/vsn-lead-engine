"""Pure v3 accepted-batch proof shape only; no intake, state or provider authority."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .billing_evidence import unique_object


@dataclass(frozen=True, repr=False)
class BatchBinding:
    workspace_id: UUID
    job_id: UUID
    operation_id: UUID
    batch_id: UUID
    provider_key: UUID
    source_code: str
    registry_namespace: str
    request_hash: str
    policy_fingerprint: str
    candidate_body_hash: str
    candidate_event_ref: str
    reserved_leads: int
    reserved_calls: int


@dataclass(frozen=True, repr=False)
class BatchManifest:
    receipt_ref: str
    body_hash: str
    issued_at: datetime
    accepted_count: int
    provider_calls: int


def ref(value, size=96):
    return isinstance(value, str) and re.fullmatch(rf"[A-Za-z0-9._:/-]{{1,{size}}}", value)


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)


def verified_batch_manifest(body, source_signature, dedupe_signature, binding):
    """A proof-shaped fixture is not signer truth, ordering, replay or intake permission."""
    try:
        if not isinstance(binding, BatchBinding):
            raise ValueError()
        for name in ("workspace_id", "job_id", "operation_id", "batch_id", "provider_key"):
            if not isinstance(getattr(binding, name), UUID):
                raise ValueError()
        for name in ("source_code", "registry_namespace", "candidate_event_ref"):
            if not ref(getattr(binding, name), 64 if name == "source_code" else 96):
                raise ValueError()
        for name in ("request_hash", "policy_fingerprint", "candidate_body_hash"):
            if not digest(getattr(binding, name)):
                raise ValueError()
        if any(
            type(n) is not int or not 1 <= n <= 2147483647
            for n in (binding.reserved_leads, binding.reserved_calls)
        ):
            raise ValueError()
        if not isinstance(body, bytes) or not 1 <= len(body) <= 16384:
            raise ValueError()
        if not digest(source_signature) or not digest(dedupe_signature):
            raise ValueError()
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
        coordinates = {f.name for f in fields(binding)} - {"reserved_leads", "reserved_calls"}
        required = coordinates | {
            "version",
            "kind",
            "source_key_id",
            "dedupe_key_id",
            "receipt_ref",
            "issued_at",
            "provider_calls",
            "records",
            "registry_contract",
            "qualification_contract",
            "registry_state",
        }
        if not isinstance(data, dict) or set(data) != required:
            raise ValueError()
        for name in coordinates:
            if data[name] != str(getattr(binding, name)):
                raise ValueError()
        if (
            type(data["version"]) is not int
            or data["version"] != 3
            or data["kind"] != "accepted-batch"
        ):
            raise ValueError()
        if (data["registry_contract"], data["qualification_contract"], data["registry_state"]) != (
            "r2-exact-objects-v1",
            "vsn-phone-usca-v1",
            "committed",
        ):
            raise ValueError()
        for name in ("source_key_id", "dedupe_key_id", "receipt_ref"):
            if not ref(data[name], 96 if name == "receipt_ref" else 64):
                raise ValueError()
        source_key = settings.SAAS_BATCH_VERIFIERS.get(binding.source_code, {}).get(
            data["source_key_id"]
        )
        dedupe_key = settings.SAAS_BATCH_DEDUPE_VERIFIERS.get(binding.registry_namespace, {}).get(
            data["dedupe_key_id"]
        )
        if (
            not isinstance(source_key, bytes)
            or not isinstance(dedupe_key, bytes)
            or min(len(source_key), len(dedupe_key)) < 32
            or source_key == dedupe_key
        ):
            raise ValueError()
        if not hmac.compare_digest(
            source_signature, hmac.new(source_key, body, hashlib.sha256).hexdigest()
        ) or not hmac.compare_digest(
            dedupe_signature, hmac.new(dedupe_key, body, hashlib.sha256).hexdigest()
        ):
            raise ValueError()
        if type(data["issued_at"]) is not int:
            raise ValueError()
        issued = datetime.fromtimestamp(data["issued_at"], UTC)
        now = timezone.now()
        if not now - timedelta(hours=24) <= issued <= now + timedelta(minutes=5):
            raise ValueError()
        if (
            type(data["provider_calls"]) is not int
            or not 1 <= data["provider_calls"] <= binding.reserved_calls
        ):
            raise ValueError()
        records = data["records"]
        if not isinstance(records, list) or not 1 <= len(records) <= min(
            25, binding.reserved_leads
        ):
            raise ValueError()
        refs, tokens = set(), set()
        for row in records:
            if (
                not isinstance(row, dict)
                or set(row) != {"record_ref", "tokens"}
                or not ref(row["record_ref"])
            ):
                raise ValueError()
            if row["record_ref"] in refs:
                raise ValueError()
            refs.add(row["record_ref"])
            values = row["tokens"]
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(
                    not isinstance(t, str) or not re.fullmatch("[nls]:[0-9a-f]{24}", t)
                    for t in values
                )
                or {t[0] for t in values} != {"n", "l", "s"}
                or tokens.intersection(values)
            ):
                raise ValueError()
            tokens.update(values)
        return BatchManifest(
            data["receipt_ref"],
            hashlib.sha256(body).hexdigest(),
            issued,
            len(records),
            data["provider_calls"],
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        UnicodeError,
        OSError,
        RecursionError,
    ):
        raise ValidationError("Batch manifest is unavailable or invalid.") from None
