"""Pure source-signed v3 zero-effect claim; never a refund or status change."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .batch_manifest import digest, ref
from .billing_evidence import unique_object


@dataclass(frozen=True, repr=False)
class NoEffectBatch:
    batch_id: UUID
    candidate_body_hash: str | None


@dataclass(frozen=True, repr=False)
class NoEffectBinding:
    workspace_id: UUID
    job_id: UUID
    operation_id: UUID
    provider_key: UUID
    source_code: str
    request_hash: str
    policy_fingerprint: str
    batches: tuple[NoEffectBatch, ...]


@dataclass(frozen=True, repr=False)
class NoEffectProof:
    receipt_ref: str
    key_id: str
    body_hash: str
    batch_set_hash: str
    batch_count: int
    issued_at: datetime


def verified_noeffect_manifest(body, signature, binding):
    """Check an explicit source claim over the exact allocated identity set.

    The caller must separately establish current rights, absent accepted payload,
    complete durable batches and qualified source authority before acting on it.
    """
    try:
        if not isinstance(binding, NoEffectBinding):
            raise ValueError()
        coordinates = ("workspace_id", "job_id", "operation_id", "provider_key")
        if any(not isinstance(getattr(binding, name), UUID) for name in coordinates):
            raise ValueError()
        if not ref(binding.source_code, 64) or not all(
            digest(value) for value in (binding.request_hash, binding.policy_fingerprint)
        ):
            raise ValueError()
        if type(binding.batches) is not tuple or len(binding.batches) > 1000:
            raise ValueError()
        expected_batches, seen = [], set()
        for item in binding.batches:
            if (
                not isinstance(item, NoEffectBatch)
                or not isinstance(item.batch_id, UUID)
                or item.batch_id in seen
                or item.candidate_body_hash is not None
                and not digest(item.candidate_body_hash)
            ):
                raise ValueError()
            seen.add(item.batch_id)
            expected_batches.append(
                {
                    "batch_id": str(item.batch_id),
                    "candidate_body_hash": item.candidate_body_hash,
                }
            )
        expected_batches.sort(key=lambda row: row["batch_id"])
        if not isinstance(body, bytes) or not 1 <= len(body) <= 262144 or not digest(signature):
            raise ValueError()
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
        expected = set(coordinates) | {
            "version",
            "kind",
            "source_code",
            "request_hash",
            "policy_fingerprint",
            "source_key_id",
            "receipt_ref",
            "issued_at",
            "provider_calls",
            "batches",
        }
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError()
        for name in coordinates + ("source_code", "request_hash", "policy_fingerprint"):
            if data[name] != str(getattr(binding, name)):
                raise ValueError()
        if (
            type(data["version"]) is not int
            or data["version"] != 3
            or data["kind"] != "source-noeffect"
            or type(data["provider_calls"]) is not int
            or data["provider_calls"] != 0
            or not ref(data["source_key_id"], 64)
            or not ref(data["receipt_ref"])
        ):
            raise ValueError()
        key = settings.SAAS_BATCH_NOEFFECT_VERIFIERS.get(binding.source_code, {}).get(
            data["source_key_id"]
        )
        if (
            not isinstance(key, bytes)
            or len(key) < 32
            or not hmac.compare_digest(signature, hmac.new(key, body, hashlib.sha256).hexdigest())
        ):
            raise ValueError()
        if (
            type(data["batches"]) is not list
            or len(data["batches"]) != len(expected_batches)
            or any(
                type(actual) is not dict
                or set(actual) != {"batch_id", "candidate_body_hash"}
                or actual != trusted
                for actual, trusted in zip(data["batches"], expected_batches, strict=True)
            )
        ):
            raise ValueError()
        if type(data["issued_at"]) is not int:
            raise ValueError()
        issued = datetime.fromtimestamp(data["issued_at"], UTC)
        now = timezone.now()
        if not now - timedelta(hours=24) <= issued <= now + timedelta(minutes=5):
            raise ValueError()
        set_bytes = json.dumps(expected_batches, sort_keys=True, separators=(",", ":")).encode(
            "ascii"
        )
        return NoEffectProof(
            data["receipt_ref"],
            data["source_key_id"],
            hashlib.sha256(body).hexdigest(),
            hashlib.sha256(set_bytes).hexdigest(),
            len(expected_batches),
            issued,
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
        raise ValidationError("No-effect manifest is unavailable or invalid.") from None
