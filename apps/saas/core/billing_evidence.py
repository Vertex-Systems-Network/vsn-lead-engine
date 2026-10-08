"""Internal normalized billing evidence only: no payment, storage or entitlement writes."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

FIELDS = {
    "version",
    "key_id",
    "event_ref",
    "issuer_code",
    "binding_id",
    "workspace_id",
    "revision",
    "issued_at",
    "valid_until",
    "active",
    "limits",
}
LIMITS = ("leads", "jobs", "provider_calls", "exports")


@dataclass(frozen=True, repr=False)
class BillingBinding:
    """Trusted server coordinates; callers must never derive these from event claims."""

    id: UUID
    workspace_id: UUID
    issuer_code: str


@dataclass(frozen=True, repr=False)
class BillingEvidence:
    event_ref: str
    key_id: str
    body_hash: str
    revision: int
    issued_at: datetime
    valid_until: datetime
    active: bool
    leads: int
    jobs: int
    provider_calls: int
    exports: int


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def verified_billing_event(body, signature, binding):
    """Exact-byte HMAC from a separately trusted normalized-event adapter.

    A valid signature is NOT payment proof, ordering/idempotency or permission to
    update entitlements. A future reconciler must obtain an enabled binding under
    workspace lock and enforce event uniqueness/contiguous revisions atomically.
    The default registry is empty. No endpoint or provider accepts these events.
    """
    try:
        if (
            not isinstance(binding, BillingBinding)
            or not isinstance(binding.id, UUID)
            or not isinstance(binding.workspace_id, UUID)
            or not isinstance(binding.issuer_code, str)
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", binding.issuer_code)
            or not isinstance(body, bytes)
            or not 1 <= len(body) <= 8192
            or not isinstance(signature, str)
            or not re.fullmatch(r"[0-9a-f]{64}", signature)
        ):
            raise ValueError()
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(data, dict) or set(data) != FIELDS:
            raise ValueError()
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError()
        for key, expected in {
            "workspace_id": str(binding.workspace_id),
            "binding_id": str(binding.id),
            "issuer_code": binding.issuer_code,
        }.items():
            if data[key] != expected:
                raise ValueError()
        for key, size in [("key_id", 64), ("event_ref", 96)]:
            if not isinstance(data[key], str) or not re.fullmatch(
                rf"[A-Za-z0-9._:-]{{1,{size}}}", data[key]
            ):
                raise ValueError()
        secret = settings.SAAS_BILLING_VERIFIERS.get(binding.issuer_code, {}).get(data["key_id"])
        if (
            not isinstance(secret, bytes)
            or len(secret) < 32
            or not hmac.compare_digest(
                signature, hmac.new(secret, body, hashlib.sha256).hexdigest()
            )
        ):
            raise ValueError()
        if type(data["revision"]) is not int or not 1 <= data["revision"] <= 2147483647:
            raise ValueError()
        if type(data["issued_at"]) is not int or type(data["active"]) is not bool:
            raise ValueError()
        issued_at = datetime.fromtimestamp(data["issued_at"], UTC)
        now = timezone.now()
        if not now - timedelta(hours=24) <= issued_at <= now + timedelta(minutes=5):
            raise ValueError()
        if type(data["valid_until"]) is not int:
            raise ValueError()
        valid_until = datetime.fromtimestamp(data["valid_until"], UTC)
        if data["active"]:
            if not max(now, issued_at) < valid_until <= issued_at + timedelta(days=366):
                raise ValueError()
        elif valid_until != issued_at:
            raise ValueError()
        limits = data["limits"]
        if not isinstance(limits, dict) or set(limits) != set(LIMITS):
            raise ValueError()
        if any(
            type(limits[key]) is not int or not 0 <= limits[key] <= 2147483647 for key in LIMITS
        ):
            raise ValueError()
        if not data["active"] and any(limits.values()):
            raise ValueError()
        return BillingEvidence(
            event_ref=data["event_ref"],
            key_id=data["key_id"],
            body_hash=hashlib.sha256(body).hexdigest(),
            revision=data["revision"],
            issued_at=issued_at,
            valid_until=valid_until,
            active=data["active"],
            **limits,
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
        raise ValidationError("Billing evidence is unavailable or invalid.") from None
