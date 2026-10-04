#!/usr/bin/env python3
"""Create and decide replay-resistant ANPOS consent records.

A production runtime must set ANPOS_AUTHENTICATED_USER from an authenticated
human session/callback. This script does not turn a self-supplied environment
variable into cryptographic identity outside that trusted boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "config" / "consent" / "consent-requests.json"


def now():
    return datetime.now(timezone.utc)


def iso(v):
    return v.isoformat()


def canonical_payload(record):
    immutable = {
        "id": record.get("id"),
        "type": record.get("type"),
        "title": record.get("title"),
        "summary": record.get("summary"),
        "proposed_changes": record.get("proposed_changes") or [],
        "affected_modules": record.get("affected_modules") or [],
        "risk": record.get("risk"),
        "owner_identity": record.get("owner_identity"),
        "requested_at": record.get("requested_at"),
        "expires_at": record.get("expires_at"),
        "nonce": record.get("nonce"),
    }
    return json.dumps(immutable, sort_keys=True, separators=(",", ":"))


def request_hash(record):
    return hashlib.sha256(canonical_payload(record).encode("utf-8")).hexdigest()


def load():
    return json.loads(FILE.read_text(encoding="utf-8"))


def save(doc):
    FILE.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def create(args):
    doc = load()
    seq = int(doc.get("next_sequence") or 1)
    request_id = f"CONSENT-{seq:06d}"
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    created = now()
    record = {
        "id": request_id,
        "type": source.get("type") or "material_change",
        "title": source.get("title") or "",
        "summary": source.get("summary") or "",
        "requested_by": source.get("requested_by") or "supervisor",
        "requested_at": iso(created),
        "request_hash": None,
        "nonce": str(uuid.uuid4()),
        "expires_at": iso(created + timedelta(hours=max(1, args.expires_hours))),
        "nonce_consumed_at": None,
        "owner_identity": source.get("owner_identity"),
        "canonical_review_reference": source.get("canonical_review_reference"),
        "email_notification_reference": source.get("email_notification_reference"),
        "proposed_changes": source.get("proposed_changes") or [],
        "affected_modules": source.get("affected_modules") or [],
        "risk": source.get("risk") or "unknown",
        "status": "pending",
        "approved_scope": [],
        "decision_by": None,
        "decision_identity_evidence_ref": None,
        "decision_at": None,
        "decision_evidence": None,
        "decision_request_hash": None,
        "implementation_reference": None,
        "verification_reference": None,
    }
    record["request_hash"] = request_hash(record)
    doc.setdefault("requests", []).append(record)
    doc["next_sequence"] = seq + 1
    if args.apply:
        save(doc)
    print(json.dumps(record, indent=2))
    if not args.apply:
        print("DRY RUN - request not persisted.")


def decide(args):
    authenticated = os.getenv("ANPOS_AUTHENTICATED_USER")
    if not authenticated:
        raise SystemExit("ANPOS_AUTHENTICATED_USER must come from the trusted authenticated runtime before recording consent.")
    if authenticated != args.decision_by:
        raise SystemExit("Decision identity does not match authenticated runtime user.")
    doc = load()
    record = next((r for r in doc.get("requests", []) if r.get("id") == args.id), None)
    if not record:
        raise SystemExit(f"Unknown consent request {args.id}.")
    if record.get("status") != "pending" or record.get("nonce_consumed_at"):
        raise SystemExit("Consent request is not pending or its nonce has already been consumed.")
    expiry = datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00"))
    if expiry <= now():
        record["status"] = "expired"
        if args.apply:
            save(doc)
        raise SystemExit("Consent request has expired.")
    if args.nonce != record.get("nonce"):
        raise SystemExit("Consent nonce mismatch.")
    calculated = request_hash(record)
    if calculated != record.get("request_hash") or args.request_hash != calculated:
        raise SystemExit("Consent request hash mismatch; changed requests require new consent.")
    decision_time = now()
    record["status"] = args.decision
    record["approved_scope"] = args.approved_scope or []
    record["decision_by"] = args.decision_by
    record["decision_identity_evidence_ref"] = args.identity_evidence_ref
    record["decision_at"] = iso(decision_time)
    record["decision_evidence"] = args.evidence_ref
    record["decision_request_hash"] = calculated
    record["nonce_consumed_at"] = iso(decision_time)
    if args.apply:
        save(doc)
    print(json.dumps(record, indent=2))
    if not args.apply:
        print("DRY RUN - decision not persisted.")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("--input", required=True)
    c.add_argument("--expires-hours", type=int, default=24)
    c.add_argument("--apply", action="store_true")
    c.set_defaults(func=create)

    d = sub.add_parser("decide")
    d.add_argument("--id", required=True)
    d.add_argument("--request-hash", required=True)
    d.add_argument("--nonce", required=True)
    d.add_argument("--decision", choices=["approved", "partially_approved", "rejected"], required=True)
    d.add_argument("--decision-by", required=True)
    d.add_argument("--identity-evidence-ref", required=True)
    d.add_argument("--evidence-ref", required=True)
    d.add_argument("--approved-scope", nargs="*")
    d.add_argument("--apply", action="store_true")
    d.set_defaults(func=decide)
    args = p.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
