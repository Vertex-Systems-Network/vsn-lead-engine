"""Pure bounded v3 candidate proof; no event persistence, source call or acceptance."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .batch_manifest import digest, ref
from .billing_evidence import unique_object
from .candidate_records import checked_candidate_records, instant


@dataclass(frozen=True, repr=False)
class CandidateBatchBinding:
    workspace_id: UUID
    job_id: UUID
    operation_id: UUID
    batch_id: UUID
    provider_key: UUID
    source_code: str
    request_hash: str
    policy_fingerprint: str
    operation_created_at: datetime
    reserved_leads: int


@dataclass(frozen=True, repr=False)
class CandidateBatchReview:
    event_ref: str
    body_hash: str
    candidate_count: int
    earliest_delete_at: datetime


def verified_batch_candidates(body, signature, binding, policy, search):
    """Trusted local policy/search still need current locks before any durable intake."""
    try:
        if not isinstance(binding, CandidateBatchBinding):
            raise ValueError()
        uuid_names = ("workspace_id", "job_id", "operation_id", "batch_id", "provider_key")
        if any(not isinstance(getattr(binding, name), UUID) for name in uuid_names):
            raise ValueError()
        if (
            not ref(binding.source_code, 64)
            or not digest(binding.request_hash)
            or not digest(binding.policy_fingerprint)
        ):
            raise ValueError()
        if type(binding.reserved_leads) is not int or not 1 <= binding.reserved_leads <= 1000:
            raise ValueError()
        if not isinstance(binding.operation_created_at, datetime) or not timezone.is_aware(
            binding.operation_created_at
        ):
            raise ValueError()
        if not isinstance(body, bytes) or not 1 <= len(body) <= 131072 or not digest(signature):
            raise ValueError()
        data = json.loads(body, object_pairs_hook=unique_object)
        coordinates = uuid_names + ("source_code", "request_hash", "policy_fingerprint")
        if not isinstance(data, dict) or set(data) != set(coordinates) | {
            "version",
            "kind",
            "source_key_id",
            "event_ref",
            "issued_at",
            "records",
        }:
            raise ValueError()
        if (
            type(data["version"]) is not int
            or data["version"] != 3
            or data["kind"] != "candidate-batch"
        ):
            raise ValueError()
        for name in coordinates:
            if data[name] != str(getattr(binding, name)):
                raise ValueError()
        if not ref(data["source_key_id"], 64) or not ref(data["event_ref"]):
            raise ValueError()
        key = settings.SAAS_BATCH_CANDIDATE_VERIFIERS.get(binding.source_code, {}).get(
            data["source_key_id"]
        )
        if (
            not isinstance(key, bytes)
            or len(key) < 32
            or not hmac.compare_digest(signature, hmac.new(key, body, hashlib.sha256).hexdigest())
        ):
            raise ValueError()
        now = timezone.now()
        issued = instant(data["issued_at"])
        if (
            not max(binding.operation_created_at - timedelta(minutes=5), now - timedelta(hours=24))
            <= issued
            <= now + timedelta(minutes=5)
        ):
            raise ValueError()
        if (
            type(search.get("result_limit")) is not int
            or not 1 <= search["result_limit"] <= binding.reserved_leads
        ):
            raise ValueError()
        if policy.code != binding.source_code:
            raise ValueError()
        review = checked_candidate_records(body, data, policy, search, now, issued)
        return CandidateBatchReview(
            review.event_ref, review.body_hash, review.candidate_count, review.earliest_delete_at
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
        raise ValidationError("Batch candidate evidence is unavailable or invalid.") from None
