"""Pure bounded v3 source-final proof; no ORM, enrollment or settlement authority."""

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
class TerminalBatch:
    batch_id: UUID
    acceptance_body_hash: str
    accepted_count: int
    provider_calls: int


@dataclass(frozen=True, repr=False)
class TerminalBinding:
    workspace_id: UUID
    job_id: UUID
    operation_id: UUID
    provider_key: UUID
    source_code: str
    request_hash: str
    policy_fingerprint: str
    reserved_leads: int
    reserved_calls: int
    batches: tuple[TerminalBatch, ...]


@dataclass(frozen=True, repr=False)
class TerminalManifest:
    receipt_ref: str
    body_hash: str
    batch_set_hash: str
    batch_count: int
    accepted_count: int
    provider_calls: int
    issued_at: datetime


def verified_terminal_manifest(body, signature, binding):
    """Compare a source-signed set with trusted accepted evidence, never infer finality."""
    try:
        if not isinstance(binding, TerminalBinding):
            raise ValueError()
        coordinates = ("workspace_id", "job_id", "operation_id", "provider_key")
        if any(not isinstance(getattr(binding, name), UUID) for name in coordinates):
            raise ValueError()
        if not ref(binding.source_code, 64) or not all(
            digest(value) for value in (binding.request_hash, binding.policy_fingerprint)
        ):
            raise ValueError()
        if any(
            type(value) is not int or not 1 <= value <= 2147483647
            for value in (binding.reserved_leads, binding.reserved_calls)
        ):
            raise ValueError()
        if type(binding.batches) is not tuple or len(binding.batches) > min(
            1000, binding.reserved_leads, binding.reserved_calls
        ):
            raise ValueError()
        rows, seen, leads, calls = [], set(), 0, 0
        for batch in binding.batches:
            if (
                not isinstance(batch, TerminalBatch)
                or not isinstance(batch.batch_id, UUID)
                or batch.batch_id in seen
                or not digest(batch.acceptance_body_hash)
                or type(batch.accepted_count) is not int
                or not 1 <= batch.accepted_count <= 25
                or type(batch.provider_calls) is not int
                or not 1 <= batch.provider_calls <= binding.reserved_calls
            ):
                raise ValueError()
            seen.add(batch.batch_id)
            leads += batch.accepted_count
            calls += batch.provider_calls
            rows.append(
                dict(
                    batch_id=str(batch.batch_id),
                    acceptance_body_hash=batch.acceptance_body_hash,
                    accepted_count=batch.accepted_count,
                    provider_calls=batch.provider_calls,
                )
            )
        if leads > binding.reserved_leads or calls > binding.reserved_calls:
            raise ValueError()
        rows.sort(key=lambda row: row["batch_id"])
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
            or data["kind"] != "source-final"
        ):
            raise ValueError()
        if not ref(data["source_key_id"], 64) or not ref(data["receipt_ref"]):
            raise ValueError()
        key = settings.SAAS_BATCH_TERMINAL_VERIFIERS.get(binding.source_code, {}).get(
            data["source_key_id"]
        )
        if (
            not isinstance(key, bytes)
            or len(key) < 32
            or not hmac.compare_digest(signature, hmac.new(key, body, hashlib.sha256).hexdigest())
        ):
            raise ValueError()
        # Equality alone would accept JSON booleans/floats as integer counts.
        if not isinstance(data["batches"], list) or len(data["batches"]) != len(rows):
            raise ValueError()
        for actual, trusted in zip(data["batches"], rows, strict=True):
            if not isinstance(actual, dict) or set(actual) != set(trusted) or actual != trusted:
                raise ValueError()
            if any(type(actual[name]) is not int for name in ("accepted_count", "provider_calls")):
                raise ValueError()
        if (
            type(data["provider_calls"]) is not int
            or not calls <= data["provider_calls"] <= binding.reserved_calls
        ):
            raise ValueError()
        if type(data["issued_at"]) is not int:
            raise ValueError()
        issued = datetime.fromtimestamp(data["issued_at"], UTC)
        now = timezone.now()
        if not now - timedelta(hours=24) <= issued <= now + timedelta(minutes=5):
            raise ValueError()
        set_bytes = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")
        return TerminalManifest(
            data["receipt_ref"],
            hashlib.sha256(body).hexdigest(),
            hashlib.sha256(set_bytes).hexdigest(),
            len(rows),
            leads,
            data["provider_calls"],
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
        raise ValidationError("Terminal manifest is unavailable or invalid.") from None
