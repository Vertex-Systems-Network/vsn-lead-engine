#!/usr/bin/env python3
"""Claim an ANPOS Worker slot with authorization + deterministic GitHub ref lock.

A real claim requires a live Supervisor, a selected/identity-verified Worker,
eligibility/capability/path/tool/budget authorization, a complete handoff envelope,
remote ref acquisition and queue-mirror persistence. A durable orchestrator must
add host-authenticated GitHub CAS persistence around this reference implementation.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "config/coordination/agent-work-queue.json"
sys.path.insert(0, str(ROOT / "scripts"))
from anpos_guard import (  # noqa: E402
    authorize_runtime_scope,
    authorize_slot_claim,
    authorize_slot_paths,
    live_supervisor,
    validate_handoff,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def infer_repo() -> str:
    if os.getenv("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    remote = subprocess.check_output(
        ["git", "config", "--get", "remote.origin.url"], cwd=ROOT, text=True
    ).strip().removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    if "github.com/" not in remote:
        raise SystemExit("Unsupported/non-GitHub remote; pass --repository and use an equivalent authenticated lock adapter.")
    return remote.split("github.com/", 1)[1]


def infer_base_sha() -> str:
    for ref in ("origin/main", "main", "HEAD"):
        try:
            return subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
        except Exception:
            pass
    raise SystemExit("Unable to resolve base SHA; pass --base-sha.")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dependency_ready(slot: dict[str, Any], slots: list[dict[str, Any]]) -> bool:
    deps = set(slot.get("dependencies") or [])
    if not deps:
        return True
    completed = {
        str(s.get("work_unit_id"))
        for s in slots
        if s.get("status") in {"merged", "completed"} and s.get("work_unit_id")
    }
    return deps.issubset(completed)


def enforce_budgets(queue: dict[str, Any], slot: dict[str, Any]) -> None:
    budget = load(ROOT / "config/runtime/budgets.json")
    limits = budget.get("limits") or {}
    max_parallel = int(limits.get("max_parallel_agents") or 1)
    max_depth = int(limits.get("max_delegation_depth") or 0)
    active_states = {"claimed", "in_progress", "blocked", "submitted_for_review", "changes_requested", "approved"}
    active = sum(1 for item in queue.get("slots", []) if isinstance(item, dict) and item.get("status") in active_states)
    if active >= max_parallel:
        raise PermissionError(f"Parallel-agent budget reached: {active}/{max_parallel} active slots.")
    depth = int(slot.get("delegation_depth") or 0)
    if depth > max_depth:
        raise PermissionError(f"Delegation depth {depth} exceeds configured maximum {max_depth}.")


def pick_slot(queue: dict[str, Any], requested: str | None) -> dict[str, Any]:
    slots = [s for s in queue.get("slots", []) if isinstance(s, dict)]
    candidates = [
        s for s in slots
        if s.get("status") == "free"
        and dependency_ready(s, slots)
        and (requested is None or s.get("id") == requested)
    ]
    if not candidates:
        raise SystemExit("No valid dependency-satisfied free slot found.")
    candidates.sort(key=lambda s: (-int(s.get("priority") or 0), str(s.get("id"))))
    return candidates[0]


def gh_ref(repo: str, ref: str, sha: str) -> None:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{ref}", "-f", f"sha={sha}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Atomic claim lost or GitHub ref creation failed. No queue claim was written.\n"
            + result.stderr.strip()
        )


def delete_gh_ref(repo: str, ref: str) -> bool:
    result = subprocess.run(
        ["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{ref}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slot-id")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--agent-type", default="generic")
    p.add_argument("--base-sha")
    p.add_argument("--repository")
    p.add_argument("--lease-minutes", type=int, default=90)
    p.add_argument("--remote-lock", action="store_true", help="Create deterministic GitHub claim ref")
    p.add_argument("--apply-state", action="store_true", help="Persist the local queue mirror after lock acquisition")
    args = p.parse_args()

    if args.remote_lock and not args.apply_state:
        raise SystemExit("Refusing a ref-only claim: --remote-lock requires --apply-state to reduce orphan locks.")

    queue = load(QUEUE)
    slot = pick_slot(queue, args.slot_id)
    enforce_budgets(queue, slot)
    supervisor_state, supervisor = live_supervisor()
    epoch = int(supervisor_state.get("coordination_epoch") or 0)
    base_sha = args.base_sha or infer_base_sha()
    repo = args.repository or infer_repo()

    # Validate the exact typed handoff/base revision before lock creation.
    slot["base_sha"] = base_sha
    validate_handoff(slot)
    agent = authorize_slot_claim(slot, args.agent_id, role="worker")
    authorize_slot_paths(slot, agent)
    authorize_runtime_scope(slot, agent)

    claim_ref = f"claims/epoch-{epoch:06d}/{slot['id']}"
    lease_id = str(uuid.uuid4())
    claimed = utcnow()
    expires = claimed + timedelta(minutes=max(5, args.lease_minutes))
    worker_fencing = f"worker:{epoch}:{lease_id}"
    identity_ref = (agent.get("runtime_identity") or {}).get("evidence_ref")

    print(json.dumps({
        "slot_id": slot["id"], "claim_ref": claim_ref, "base_sha": base_sha,
        "agent_id": args.agent_id, "agent_identity_ref": identity_ref,
        "lease_id": lease_id, "lease_expires_at": iso(expires),
        "coordination_epoch": epoch, "supervisor_fencing_token": supervisor.get("fencing_token"),
        "worker_fencing_token": worker_fencing,
    }, indent=2))

    if not args.remote_lock:
        print("DRY RUN - authorization/budget checks passed, but remote lock was not created; this is not a claim.")
        return 0

    gh_ref(repo, claim_ref, base_sha)
    try:
        slot.update({
            "status": "claimed", "claim_ref": claim_ref, "claim_branch": claim_ref,
            "claimant": args.agent_id, "claimant_identity_ref": identity_ref,
            "agent_type": args.agent_type, "base_sha": base_sha, "claim_id": lease_id,
            "claim_nonce": lease_id, "lease_status": "active", "lease_expires_at": iso(expires),
            "coordination_epoch": epoch, "claimed_at": iso(claimed), "heartbeat_at": iso(claimed),
            "fencing_token": worker_fencing,
        })
        queue["updated_at"] = iso(claimed)
        QUEUE.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        rolled_back = delete_gh_ref(repo, claim_ref)
        status = "rolled back remote claim ref" if rolled_back else "ORPHAN REF REQUIRES SUPERVISOR RECOVERY"
        raise SystemExit(f"Queue mirror persistence failed: {exc}; {status}.") from exc

    print("Remote lock won and authorized queue mirror updated. Persist through trusted coordination GitHub CAS before substantive work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
