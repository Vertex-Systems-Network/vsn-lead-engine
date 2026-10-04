#!/usr/bin/env python3
"""Fenced compare-and-swap gateway for shared ANPOS coordination JSON.

This is a repository-local reference implementation. A durable remote runtime
must perform equivalent authorization and compare GitHub content/blob SHA before
committing the mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from anpos_guard import require_verified_agent, verify_fencing  # noqa: E402

ALLOWED_TARGETS = {
    "config/coordination/agent-work-queue.json",
    "config/coordination/agent-alerts.json",
    "config/coordination/merge-events.json",
    "config/ai/project-state.json",
    "config/traceability/requirements-traceability.json",
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json_text(path: Path):
    text = path.read_text(encoding="utf-8")
    return text, json.loads(text)


def validate_queue_transitions(old, new) -> None:
    machine = json.loads((ROOT / "config/protocol/state-machine.json").read_text(encoding="utf-8"))
    transitions = machine.get("worker_slot_transitions") or {}
    old_slots = {str(x.get("id")): x for x in old.get("slots", []) if isinstance(x, dict) and x.get("id")}
    new_slots = {str(x.get("id")): x for x in new.get("slots", []) if isinstance(x, dict) and x.get("id")}
    removed = set(old_slots) - set(new_slots)
    if removed:
        raise PermissionError(f"Gateway refuses silent slot deletion: {sorted(removed)}")
    for slot_id, previous in old_slots.items():
        current = new_slots[slot_id]
        before = previous.get("status")
        after = current.get("status")
        if before != after and after not in set(transitions.get(before, [])):
            raise PermissionError(f"Illegal slot transition {slot_id}: {before} -> {after}")
        # Claim ownership/fencing cannot silently change on an already active slot.
        if before in {"claimed", "in_progress", "blocked", "submitted_for_review", "changes_requested", "approved"}:
            for key in ("claimant", "claim_id", "coordination_epoch", "fencing_token"):
                if previous.get(key) != current.get(key):
                    raise PermissionError(f"Active slot {slot_id} cannot silently change {key} through generic mutation gateway.")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, choices=sorted(ALLOWED_TARGETS))
    p.add_argument("--input", required=True, help="Path to complete replacement JSON document")
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--supervisor-agent-id", required=True)
    p.add_argument("--coordination-epoch", type=int, required=True)
    p.add_argument("--fencing-token", required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    require_verified_agent(args.supervisor_agent_id, "supervisor")
    verify_fencing(args.coordination_epoch, args.fencing_token, args.supervisor_agent_id)

    target = ROOT / args.target
    old_text, old_doc = load_json_text(target)
    actual = digest(old_text)
    if actual != args.expected_sha256:
        raise SystemExit(f"CAS mismatch for {args.target}: expected {args.expected_sha256}, actual {actual}.")

    input_path = Path(args.input).resolve()
    new_doc = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(new_doc, dict):
        raise SystemExit("Replacement JSON must be an object.")

    if args.target == "config/coordination/agent-work-queue.json":
        validate_queue_transitions(old_doc, new_doc)

    rendered = json.dumps(new_doc, indent=2) + "\n"
    print(json.dumps({
        "target": args.target,
        "old_sha256": actual,
        "new_sha256": digest(rendered),
        "authorized_by": args.supervisor_agent_id,
        "coordination_epoch": args.coordination_epoch,
    }, indent=2))

    if not args.apply:
        print("DRY RUN - authorized mutation validated but not written.")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print("Authorized fenced local mutation written. Remote orchestrators must still commit with GitHub blob-SHA CAS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
