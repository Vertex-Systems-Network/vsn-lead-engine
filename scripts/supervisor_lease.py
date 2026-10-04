#!/usr/bin/env python3
"""Acquire the single-Supervisor lease using authenticated, epoch-fenced GitHub refs.

Heartbeat/release/recovery are implemented by scripts/lease_control.py. A durable
orchestrator must authenticate the runtime principal and persist state with CAS.
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

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "config/coordination/supervisor-state.json"
sys.path.insert(0, str(ROOT / "scripts"))
from anpos_guard import require_verified_agent  # noqa: E402


def now():
    return datetime.now(timezone.utc)


def iso(v):
    return v.isoformat()


def repo_name() -> str:
    if os.getenv("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    remote = subprocess.check_output(
        ["git", "config", "--get", "remote.origin.url"], cwd=ROOT, text=True
    ).strip().removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    if "github.com/" not in remote:
        raise SystemExit("Unsupported/non-GitHub remote; use an equivalent authenticated election adapter.")
    return remote.split("github.com/", 1)[1]


def base_sha() -> str:
    for ref in ("origin/main", "main", "HEAD"):
        try:
            return subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
        except Exception:
            pass
    raise SystemExit("Unable to resolve base SHA; pass --base-sha.")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def acquire_remote(repo: str, ref: str, sha: str) -> None:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{ref}", "-f", f"sha={sha}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Supervisor election lost or GitHub ref creation failed.\n" + result.stderr.strip())


def delete_remote(repo: str, ref: str) -> bool:
    result = subprocess.run(
        ["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{ref}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True)
    p.add_argument("--agent-type", default="supervisor")
    p.add_argument("--lease-minutes", type=int, default=30)
    p.add_argument("--repository")
    p.add_argument("--base-sha")
    p.add_argument("--remote-lock", action="store_true")
    p.add_argument("--apply-state", action="store_true")
    args = p.parse_args()

    if args.remote_lock and not args.apply_state:
        raise SystemExit("Refusing a ref-only election: --remote-lock requires --apply-state to reduce orphan elections.")

    agent = require_verified_agent(args.agent_id, "supervisor")
    if (agent.get("permissions") or {}).get("repository_admin") is not True and "coordination_admin" not in set(agent.get("capabilities") or []):
        raise SystemExit("Selected Supervisor lacks repository_admin or coordination_admin authorization.")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    current = state.get("supervisor") or {}
    expiry = parse_time(current.get("lease_expires_at"))
    if current.get("status") == "active" and expiry and expiry > now():
        raise SystemExit(
            f"Active Supervisor lease still valid for {current.get('agent_id')} until {expiry.isoformat()}."
        )

    epoch = int(state.get("coordination_epoch") or 0) + 1
    lease_id = str(uuid.uuid4())
    acquired = now()
    expires = acquired + timedelta(minutes=max(5, args.lease_minutes))
    sha = args.base_sha or base_sha()
    repo = args.repository or repo_name()
    election_ref = f"supervisor/epoch-{epoch:06d}"
    fencing = f"supervisor:{epoch}:{lease_id}"
    identity_ref = (agent.get("runtime_identity") or {}).get("evidence_ref")

    print(json.dumps({
        "epoch": epoch,
        "election_ref": election_ref,
        "lease_id": lease_id,
        "fencing_token": fencing,
        "expires_at": iso(expires),
        "agent_identity_ref": identity_ref,
    }, indent=2))
    if not args.remote_lock:
        print("DRY RUN - authorization passed, but no Supervisor lease was acquired.")
        return 0

    acquire_remote(repo, election_ref, sha)
    try:
        state["coordination_epoch"] = epoch
        state["status"] = "active"
        state["supervisor"] = {
            "status": "active",
            "agent_id": args.agent_id,
            "agent_type": args.agent_type,
            "identity_ref": identity_ref,
            "branch": election_ref,
            "active_module_id": None,
            "active_work_unit_id": None,
            "started_at": iso(acquired),
            "heartbeat_at": iso(acquired),
            "lease_id": lease_id,
            "lease_status": "active",
            "lease_expires_at": iso(expires),
            "fencing_token": fencing,
            "election_ref": election_ref,
        }
        state["last_reconciled_main_sha"] = sha
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        rolled_back = delete_remote(repo, election_ref)
        status = "rolled back election ref" if rolled_back else "ORPHAN ELECTION REF REQUIRES RECOVERY"
        raise SystemExit(f"Supervisor state persistence failed: {exc}; {status}.") from exc

    print(
        "Supervisor lease acquired and local mirror updated. Persist through the trusted coordination gateway; use lease_control.py for heartbeat/release/recovery."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
