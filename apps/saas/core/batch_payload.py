"""Pure paired v3 proof-to-payload checks; never durable intake or settlement."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from rest_framework.exceptions import ValidationError

from .batch_candidates import verified_batch_candidates
from .batch_manifest import BatchBinding, verified_batch_manifest
from .billing_evidence import unique_object
from .candidate_records import instant


@dataclass(frozen=True, slots=True, repr=False)
class CheckedBatchRecord:
    record_ref: str
    country: str
    category: str
    fields: tuple
    observed_at: datetime
    delete_at: datetime
    purpose: str
    retention_version: str
    tokens: tuple


def verified_batch_payload(
    candidate_body,
    candidate_signature,
    body,
    source_signature,
    dedupe_signature,
    candidate_binding,
    registry_namespace,
    reserved_calls,
    policy,
    search,
):
    """Return immutable in-memory rows after exact paired proofs, not acceptance.

    The caller still needs locked current actor/rights/reservation, durable replay,
    original aggregate caps and exact isolated R2 authority before persisting.
    Sensitive rows have suppressed repr and are never a logging/recovery artifact.
    """
    review = verified_batch_candidates(
        candidate_body, candidate_signature, candidate_binding, policy, search
    )
    binding = BatchBinding(
        candidate_binding.workspace_id,
        candidate_binding.job_id,
        candidate_binding.operation_id,
        candidate_binding.batch_id,
        candidate_binding.provider_key,
        candidate_binding.source_code,
        registry_namespace,
        candidate_binding.request_hash,
        candidate_binding.policy_fingerprint,
        review.body_hash,
        review.event_ref,
        candidate_binding.reserved_leads,
        reserved_calls,
    )
    manifest = verified_batch_manifest(body, source_signature, dedupe_signature, binding)
    try:
        candidates = json.loads(candidate_body, object_pairs_hook=unique_object)
        accepted = json.loads(body, object_pairs_hook=unique_object)
        candidate_key = settings.SAAS_BATCH_CANDIDATE_VERIFIERS[binding.source_code][
            candidates["source_key_id"]
        ]
        dedupe_key = settings.SAAS_BATCH_DEDUPE_VERIFIERS[registry_namespace][
            accepted["dedupe_key_id"]
        ]
        if candidate_key == dedupe_key or manifest.issued_at < instant(
            candidates["issued_at"]
        ) - timedelta(minutes=5):
            raise ValueError()
        tokens = {row["record_ref"]: tuple(row["tokens"]) for row in accepted["records"]}
        if review.candidate_count != manifest.accepted_count or set(tokens) != {
            row["record_ref"] for row in candidates["records"]
        }:
            raise ValueError()
        rows = []
        for row in candidates["records"]:
            values = tokens[row["record_ref"]]
            # Match the original engine domain/name/location/source fingerprint set.
            expected = {"n", "l", "s", "d"} if row["fields"].get("website") else {"n", "l", "s"}
            if {t[0] for t in values} != expected:
                raise ValueError()
            observed = instant(row["observed_at"])
            rows.append(
                CheckedBatchRecord(
                    row["record_ref"],
                    row["country"],
                    row["category"],
                    tuple(sorted(row["fields"].items())),
                    observed,
                    observed
                    + timedelta(seconds=policy.controls["result_contract"]["max_age_seconds"]),
                    row["purpose"],
                    row["retention_version"],
                    values,
                )
            )
        return review, manifest, tuple(rows)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        OSError,
        RecursionError,
    ):
        raise ValidationError("Paired batch payload evidence is unavailable or invalid.") from None
