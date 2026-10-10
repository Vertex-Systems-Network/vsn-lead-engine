"""Queued-job fulfilment through the existing v2 single-source result path.

The worker never bypasses a gate: every step goes through the same lease,
write-ahead, candidate and dual-attested acceptance services that tests already
pin. Attestations are produced by the dev-only local signer, so with the
default empty verifier registries every fulfilment fails closed.
"""

import hashlib
import hmac
import json
import logging
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .accepted_results import accept_results
from .attempts import claim_pre_dispatch
from .candidate_events import record_candidate_review
from .dispatch import begin_dispatch, mark_outcome_unknown
from .models import AcceptedFingerprint, Entitlement, JobOutbox, Membership, SourcePolicy
from .receipts import reconcile_receipt
from .sources import adapter_for

logger = logging.getLogger(__name__)

PHONE = re.compile(r"\+1[2-9][0-9]{2}[2-9][0-9]{6}")
RECORD_FIELDS = ("business_name", "phone", "city", "website", "address")
MAX_BATCH = 25


def _keys():
    keys = settings.SAAS_LOCAL_SIGNER_KEYS
    if not keys:
        raise ImproperlyConfigured(
            "Job fulfilment requires SAAS_LOCAL_FULFILMENT=1 (dev) or SAAS_FULFILMENT_KEYS_FILE."
        )
    return keys


def _signed(role, data):
    body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return body, hmac.new(_keys()[role], body, hashlib.sha256).hexdigest()


def _token(prefix, value):
    digest = hmac.new(_keys()["dedupe"], f"{prefix}|{value}".encode(), hashlib.sha256)
    return f"{prefix}:{digest.hexdigest()[:24]}"


def _tokens(source_code, lead):
    name = " ".join(lead["business_name"].lower().split())
    tokens = [
        _token("s", f"{source_code}|{lead['source_id']}"),
        _token("n", lead["phone"]),
        _token("l", f"{name}|{lead['city'].lower()}|{lead.get('region', '').lower()}"),
    ]
    if lead.get("website"):
        host = (urlparse(lead["website"]).hostname or lead["website"]).lower()
        tokens.append(_token("d", host.removeprefix("www.")))
    return tokens


def _identity(operation):
    return {
        "operation_id": str(operation.id),
        "workspace_id": str(operation.workspace_id),
        "job_id": str(operation.job_id),
        "source_code": operation.source_code,
        "provider_key": str(operation.provider_key),
        "request_hash": operation.request_hash,
        "policy_fingerprint": operation.policy_fingerprint,
    }


def select_records(operation, policy, search, leads, cap):
    """Eligible, in-scope, batch- and workspace-unique records, at most ``cap``."""
    rights = policy.controls["result_contract"]
    allowed = set(rights["display_fields"]) & set(rights["storage_fields"])
    required = {"business_name" if f == "name" else f for f in search["required_fields"]}
    seen = set(
        AcceptedFingerprint.objects.filter(workspace_id=operation.workspace_id).values_list(
            "token", flat=True
        )
    )
    now = int(timezone.now().timestamp())
    selected = []
    for lead in leads:
        if len(selected) >= cap:
            break
        if (
            lead["country"] not in search["countries"]
            or lead["category"] not in search["categories"]
        ):
            continue
        fields = {k: lead[k] for k in RECORD_FIELDS if lead.get(k) and k in allowed}
        if search["statuses"]:
            if "status" not in allowed or lead.get("status", "active") not in search["statuses"]:
                continue
            fields["status"] = lead.get("status", "active")
        if not required <= set(fields) or not PHONE.fullmatch(fields.get("phone", "")):
            continue
        if "business_name" not in fields:
            continue
        lead = {**lead, "website": fields.get("website", "")}
        tokens = _tokens(operation.source_code, lead)
        if seen.intersection(tokens):
            continue
        seen.update(tokens)
        ref = lead["source_id"]
        selected.append(
            (
                {
                    "record_ref": ref,
                    "country": lead["country"],
                    "category": lead["category"],
                    "observed_at": now,
                    "fields": fields,
                    "field_lineage": {key: ref for key in fields},
                    "purpose": rights["purpose"],
                    "retention_version": rights["retention_version"],
                },
                tokens,
            )
        )
    return selected


def _admin(workspace_id):
    membership = (
        Membership.objects.filter(workspace_id=workspace_id, role__in=["owner", "admin"])
        .select_related("user")
        .order_by("-role", "id")
        .first()
    )
    if membership is None or not membership.user.is_active:
        raise ImproperlyConfigured("Workspace has no active administrator to settle results.")
    return membership.user


def fulfil_outbox(outbox_id):
    """Run one queued intent end to end. Returns completed, empty, unknown or skipped."""
    intent = JobOutbox.objects.select_related("job").get(pk=outbox_id)
    codes = list(intent.source_snapshot)
    enabled = len(codes) == 1 and codes[0] in settings.SAAS_FULFILMENT_SOURCES
    adapter = adapter_for(codes[0]) if enabled else None
    if adapter is None:
        return "skipped"
    job = intent.job
    actor = _admin(job.workspace_id)
    lease = claim_pre_dispatch(outbox_id)
    operation = begin_dispatch(outbox_id, lease.token)[0]
    try:
        policy = SourcePolicy.objects.get(pk=operation.source_code)
        entitlement = Entitlement.objects.get(workspace_id=job.workspace_id)
        cap = min(MAX_BATCH, job.search["result_limit"], entitlement.lead_limit)
        known = set(
            AcceptedFingerprint.objects.filter(workspace_id=job.workspace_id).values_list(
                "token", flat=True
            )
        )
        leads = adapter.fetch(
            job.search,
            cap,
            is_new=lambda lead: not known.intersection(_tokens(operation.source_code, lead)),
        )
        selected = select_records(operation, policy, job.search, leads, cap)
        identity = _identity(operation)
        now = int(timezone.now().timestamp())
        if not selected:
            reconcile_receipt(
                actor,
                job.workspace_id,
                operation.id,
                *_signed(
                    "receipt",
                    {
                        **identity,
                        "version": 1,
                        "key_id": "local-receipt",
                        "receipt_ref": f"local-noeffect:{operation.id}",
                        "outcome": "noeffect",
                        "provider_calls": 0,
                        "issued_at": now,
                    },
                ),
            )
            return "empty"
        candidate_body, candidate_sig = _signed(
            "candidate",
            {
                **identity,
                "version": 1,
                "key_id": "local-candidate",
                "event_ref": f"local-candidates:{operation.id}",
                "issued_at": now,
                "records": [record for record, _ in selected],
            },
        )
        candidate, _ = record_candidate_review(
            actor, job.workspace_id, operation.id, candidate_body, candidate_sig
        )
        acceptance = {
            **identity,
            "version": 2,
            "kind": "accepted-results",
            "key_id": "local-acceptance",
            "dedupe_key_id": "local-dedupe",
            "receipt_ref": f"local-accept:{operation.id}",
            "candidate_event_ref": candidate.event_ref,
            "candidate_body_hash": candidate.body_hash,
            "registry_namespace": f"saas-results/v1/{job.workspace_id}",
            "registry_contract": "r2-exact-objects-v1",
            "qualification_contract": "vsn-phone-usca-v1",
            "registry_state": "committed",
            "issued_at": now,
            "provider_calls": 1,
            "records": [
                {"record_ref": record["record_ref"], "tokens": tokens}
                for record, tokens in selected
            ],
        }
        body, source_sig = _signed("acceptance", acceptance)
        dedupe_sig = hmac.new(_keys()["dedupe"], body, hashlib.sha256).hexdigest()
        accept_results(
            actor,
            job.workspace_id,
            operation.id,
            candidate_body,
            candidate_sig,
            body,
            source_sig,
            dedupe_sig,
        )
        return "completed"
    except Exception:
        logger.exception("Fulfilment of job %s failed; outcome left unknown.", job.id)
        mark_outcome_unknown(actor, job.workspace_id, operation.id)
        return "unknown"


def run_pending(limit=25):
    """Fulfil up to ``limit`` oldest queued v2 intents; returns outcome counts."""
    _keys()
    limit = max(1, min(int(limit), 100))
    counts = {"completed": 0, "empty": 0, "unknown": 0, "skipped": 0, "conflict": 0}
    ids = (
        JobOutbox.objects.filter(status="pending", job__status="queued", result_protocol=2)
        .order_by("created_at")[:limit]
        .values_list("id", flat=True)
    )
    for outbox_id in list(ids):
        try:
            counts[fulfil_outbox(outbox_id)] += 1
        except Exception:
            # Lease/preflight refusals (expired intent, inactive entitlement, changed
            # policy) leave the intent pending for normal expiry; nothing was started.
            logger.warning("Job intent %s was not dispatched.", outbox_id, exc_info=True)
            counts["conflict"] += 1
    return counts
