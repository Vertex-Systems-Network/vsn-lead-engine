#!/usr/bin/env python3
"""Heartbeat, release and recover ANPOS coordination leases.

This reference implementation mutates local mirrors and optionally GitHub refs.
A production orchestrator must wrap writes in authenticated compare-and-swap
persistence and audit them.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "config/coordination/agent-work-queue.json"
SUPERVISOR = ROOT / "config/coordination/supervisor-state.json"
sys.path.insert(0, str(ROOT / "scripts"))
from anpos_guard import live_supervisor, require_verified_agent, verify_fencing  # noqa: E402


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


def repo_name() -> str:
    if os.getenv("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    remote = subprocess.check_output(
        ["git", "config", "--get", "remote.origin.url"], cwd=ROOT, text=True
    ).strip().removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    if "github.com/" not in remote:
        raise SystemExit("Unable to infer GitHub repository; pass --repository.")
    return remote.split("github.com/", 1)[1]


def delete_ref(repo: str, ref: str) -> None:
    result = subprocess.run(
        ["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{ref}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Remote ref deletion failed; preserve state as orphaned/recovery-required.\n" + result.stderr.strip())


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def find_slot(queue, slot_id):
    for slot in queue.get("slots", []):
        if isinstance(slot, dict) and slot.get("id") == slot_id:
            return slot
    raise SystemExit(f"Unknown slot {slot_id}.")


def worker_heartbeat(args) -> None:
    agent = require_verified_agent(args.agent_id, "worker")
    queue = load(QUEUE)
    slot = find_slot(queue, args.slot_id)
    state, _ = live_supervisor()
    if slot.get("claimant") != args.agent_id:
        raise SystemExit("Worker does not own this slot.")
    if slot.get("fencing_token") != args.worker_fencing_token:
        raise SystemExit("Worker fencing token mismatch.")
    if int(slot.get("coordination_epoch") or -1) != int(state.get("coordination_epoch") or 0):
        raise SystemExit("Worker claim belongs to a stale coordination epoch.")
    if slot.get("lease_status") != "active":
        raise SystemExit(f"Worker lease is not active: {slot.get('lease_status')}.")
    identity_ref = (agent.get("runtime_identity") or {}).get("evidence_ref")
    if slot.get("claimant_identity_ref") != identity_ref:
        raise SystemExit("Worker runtime identity evidence no longer matches the claim.")
    heartbeat = now()
    slot["heartbeat_at"] = iso(heartbeat)
    slot["lease_expires_at"] = iso(heartbeat + timedelta(minutes=max(5, args.lease_minutes)))
    queue["updated_at"] = iso(heartbeat)
    write(QUEUE, queue)
    print("Worker lease heartbeat recorded. Persist through trusted coordination CAS before relying on it remotely.")


def worker_release(args) -> None:
    require_verified_agent(args.supervisor_agent_id, "supervisor")
    verify_fencing(args.coordination_epoch, args.supervisor_fencing_token, args.supervisor_agent_id)
    queue = load(QUEUE)
    slot = find_slot(queue, args.slot_id)
    if slot.get("lease_status") not in {"active", "expired", "orphaned"}:
        raise SystemExit(f"Slot lease cannot be released/recovered from state {slot.get('lease_status')}.")
    if args.remote_unlock:
        ref = slot.get("claim_ref") or slot.get("claim_branch")
        if ref:
            delete_ref(args.repository or repo_name(), ref)
    slot["lease_status"] = "released" if args.disposition == "release" else "recovered"
    slot["released_at"] = iso(now())
    if args.disposition == "release":
        slot["status"] = "canceled"
    elif args.disposition == "reopen":
        # Supervisor must have inspected branch/PR evidence before using reopen.
        slot.update({
            "status": "free", "claim_ref": None, "claim_branch": None, "claimant": None,
            "claimant_identity_ref": None, "agent_type": None, "claim_id": None, "claim_nonce": None,
            "coordination_epoch": None, "fencing_token": None, "lease_expires_at": None,
            "claimed_at": None, "heartbeat_at": None,
        })
        slot["lease_status"] = "recovered"
    queue["updated_at"] = iso(now())
    write(QUEUE, queue)
    print(f"Worker lease disposition recorded: {args.disposition}.")


def supervisor_heartbeat(args) -> None:
    require_verified_agent(args.agent_id, "supervisor")
    state = verify_fencing(args.coordination_epoch, args.fencing_token, args.agent_id)
    heartbeat = now()
    state["supervisor"]["heartbeat_at"] = iso(heartbeat)
    state["supervisor"]["lease_expires_at"] = iso(heartbeat + timedelta(minutes=max(5, args.lease_minutes)))
    state["supervisor"]["lease_status"] = "active"
    write(SUPERVISOR, state)
    print("Supervisor lease heartbeat recorded.")


def supervisor_release(args) -> None:
    require_verified_agent(args.agent_id, "supervisor")
    state = verify_fencing(args.coordination_epoch, args.fencing_token, args.agent_id)
    ref = state.get("supervisor", {}).get("election_ref")
    if args.remote_unlock and ref:
        delete_ref(args.repository or repo_name(), ref)
    state["supervisor"]["status"] = "relinquished"
    state["supervisor"]["lease_status"] = "released"
    state["supervisor"]["lease_expires_at"] = iso(now())
    state["supervisor"]["heartbeat_at"] = iso(now())
    state["status"] = "relinquished"
    write(SUPERVISOR, state)
    print("Supervisor lease relinquished.")


def recover_ref(args) -> None:
    require_verified_agent(args.supervisor_agent_id, "supervisor")
    verify_fencing(args.coordination_epoch, args.supervisor_fencing_token, args.supervisor_agent_id)
    if not (args.ref.startswith("claims/") or args.ref.startswith("supervisor/")):
        raise SystemExit("Recovery only permits ANPOS coordination refs.")
    current = load(SUPERVISOR).get("supervisor", {}).get("election_ref")
    if args.ref == current:
        raise SystemExit("Refusing to delete the active Supervisor election ref through orphan recovery.")
    delete_ref(args.repository or repo_name(), args.ref)
    print("Orphan/stale coordination ref removed after Supervisor authorization.")


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)

    wh = sub.add_parser("worker-heartbeat")
    wh.add_argument("--slot-id", required=True)
    wh.add_argument("--agent-id", required=True)
    wh.add_argument("--worker-fencing-token", required=True)
    wh.add_argument("--lease-minutes", type=int, default=90)
    wh.set_defaults(func=worker_heartbeat)

    wr = sub.add_parser("worker-release")
    wr.add_argument("--slot-id", required=True)
    wr.add_argument("--supervisor-agent-id", required=True)
    wr.add_argument("--coordination-epoch", type=int, required=True)
    wr.add_argument("--supervisor-fencing-token", required=True)
    wr.add_argument("--disposition", choices=["release", "reopen"], required=True)
    wr.add_argument("--repository")
    wr.add_argument("--remote-unlock", action="store_true")
    wr.set_defaults(func=worker_release)

    sh = sub.add_parser("supervisor-heartbeat")
    sh.add_argument("--agent-id", required=True)
    sh.add_argument("--coordination-epoch", type=int, required=True)
    sh.add_argument("--fencing-token", required=True)
    sh.add_argument("--lease-minutes", type=int, default=30)
    sh.set_defaults(func=supervisor_heartbeat)

    sr = sub.add_parser("supervisor-release")
    sr.add_argument("--agent-id", required=True)
    sr.add_argument("--coordination-epoch", type=int, required=True)
    sr.add_argument("--fencing-token", required=True)
    sr.add_argument("--repository")
    sr.add_argument("--remote-unlock", action="store_true")
    sr.set_defaults(func=supervisor_release)

    rr = sub.add_parser("recover-ref")
    rr.add_argument("--ref", required=True)
    rr.add_argument("--supervisor-agent-id", required=True)
    rr.add_argument("--coordination-epoch", type=int, required=True)
    rr.add_argument("--supervisor-fencing-token", required=True)
    rr.add_argument("--repository")
    rr.set_defaults(func=recover_ref)

    args = p.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
