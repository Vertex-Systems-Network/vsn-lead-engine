#!/usr/bin/env python3
"""Shared ANPOS authorization/fencing helpers.

Repository policy is only one layer. Privileged coordination operations require
a host-authenticated runtime principal. A self-supplied agent/model name is not
identity proof.
"""
from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now() -> datetime:
    return datetime.now(timezone.utc)


def runtime_principal() -> str | None:
    return os.getenv("ANPOS_RUNTIME_PRINCIPAL") or os.getenv("GITHUB_ACTOR_ID") or os.getenv("GITHUB_ACTOR")


def _agent_id(record: Any) -> str | None:
    if isinstance(record, str):
        return record
    if isinstance(record, dict):
        value = record.get("id")
        return str(value) if value else None
    return None


def selected_agent(agent_id: str) -> dict[str, Any]:
    catalog = load_json("config/ai/agent-catalog.json")
    for record in catalog.get("selected_agents", []):
        if _agent_id(record) == agent_id:
            if not isinstance(record, dict):
                raise PermissionError(f"Selected agent {agent_id} lacks a structured verified identity record.")
            return record
    raise PermissionError(f"Agent {agent_id} is not in the selected child-project agent pool.")


def require_verified_agent(agent_id: str, role: str) -> dict[str, Any]:
    agent = selected_agent(agent_id)
    if agent.get("identity_verified") is not True:
        raise PermissionError(f"Agent {agent_id} identity is not verified by the active runtime.")
    roles = {str(v).lower() for v in (agent.get("roles") or [])}
    if role.lower() not in roles:
        raise PermissionError(f"Agent {agent_id} is not authorized for role {role}.")
    identity = agent.get("runtime_identity") or {}
    expected_principal = identity.get("principal_id")
    if not expected_principal or not identity.get("evidence_ref") or not identity.get("verified_at"):
        raise PermissionError(f"Agent {agent_id} has incomplete runtime identity evidence.")
    actual_principal = runtime_principal()
    if not actual_principal:
        raise PermissionError("Privileged ANPOS operation requires a host-authenticated runtime principal.")
    if str(actual_principal) != str(expected_principal):
        raise PermissionError(f"Runtime principal {actual_principal} does not match selected agent identity {expected_principal}.")
    expires = parse_time(identity.get("expires_at"))
    if expires and expires <= now():
        raise PermissionError(f"Agent {agent_id} runtime identity evidence is expired.")
    return agent


def live_supervisor() -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_json("config/coordination/supervisor-state.json")
    supervisor = state.get("supervisor") or {}
    expiry = parse_time(supervisor.get("lease_expires_at"))
    if supervisor.get("status") != "active" or supervisor.get("lease_status") != "active" or not expiry or expiry <= now():
        raise PermissionError("No live authoritative Supervisor lease exists for Worker dispatch.")
    return state, supervisor


def _matches_eligibility(slot: dict[str, Any], agent: dict[str, Any], role: str) -> bool:
    values = {str(v) for v in (slot.get("eligibility") or [])}
    if not values or "ANY" in values:
        return True
    ids = {str(agent.get("id")), str(agent.get("provider", "")), role}
    ids.update(str(v) for v in (agent.get("capabilities") or []))
    return bool(values & ids)


def authorize_slot_claim(slot: dict[str, Any], agent_id: str, role: str = "worker") -> dict[str, Any]:
    agent = require_verified_agent(agent_id, role)
    if not _matches_eligibility(slot, agent, role):
        raise PermissionError(f"Agent {agent_id} does not satisfy slot eligibility {slot.get('eligibility')}.")
    required_roles = {str(v).lower() for v in (slot.get("required_roles") or [])}
    if required_roles and role.lower() not in required_roles:
        raise PermissionError(f"Slot requires role(s) {sorted(required_roles)}; caller role is {role}.")
    required_caps = {str(v) for v in (slot.get("required_capabilities") or [])}
    agent_caps = {str(v) for v in (agent.get("capabilities") or [])}
    missing = required_caps - agent_caps
    if missing:
        raise PermissionError(f"Agent {agent_id} is missing capabilities: {sorted(missing)}")
    if "SUPERVISOR_ONLY" in {str(v) for v in (slot.get("eligibility") or [])} and role.lower() != "supervisor":
        raise PermissionError("SUPERVISOR_ONLY work cannot be claimed by a Worker.")
    return agent


def path_allowed(agent: dict[str, Any], path: str) -> bool:
    permissions = agent.get("permissions") or {}
    denied = permissions.get("denied_paths") or []
    allowed = permissions.get("allowed_paths") or []
    if not allowed:
        return False
    normalized = path.lstrip("/")
    if any(fnmatch.fnmatch(normalized, p.lstrip("/")) for p in denied):
        return False
    return any(fnmatch.fnmatch(normalized, p.lstrip("/")) for p in allowed)


def _literal_prefix(pattern: str) -> str:
    value = pattern.lstrip("/")
    for marker in ("*", "?", "["):
        if marker in value:
            value = value.split(marker, 1)[0]
    return value.rstrip("/")


def _patterns_overlap(a: str, b: str) -> bool:
    pa, pb = _literal_prefix(a), _literal_prefix(b)
    if not pa or not pb:
        return True
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


def authorize_slot_paths(slot: dict[str, Any], agent: dict[str, Any]) -> None:
    capabilities = {str(v) for v in (agent.get("capabilities") or [])}
    protected = load_json("config/security/control-plane-policy.json").get("protected_paths") or []
    for path in slot.get("allowed_paths") or []:
        if not path_allowed(agent, str(path)):
            raise PermissionError(f"Agent {agent.get('id')} is not authorized for slot path {path}.")
        if "control_plane_write" not in capabilities and any(_patterns_overlap(str(path), str(p)) for p in protected):
            raise PermissionError(f"Slot path {path} overlaps protected ANPOS control plane without control_plane_write capability.")


def _scope_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(v) for v in value if str(v)}
    text = str(value).strip()
    if not text or text in {"none", "no_pm", "no_access", "none_by_default", "no_secrets", "no_deploy"}:
        return set()
    return {text}


def _enforce_scope_subset(label: str, requested: Any, allowed: Any) -> None:
    requested_set = _scope_set(requested)
    allowed_set = _scope_set(allowed)
    if requested_set and "*" not in allowed_set and not requested_set.issubset(allowed_set):
        raise PermissionError(f"Agent lacks requested {label}: {sorted(requested_set - allowed_set)}")


def authorize_runtime_scope(slot: dict[str, Any], agent: dict[str, Any]) -> None:
    permissions = agent.get("permissions") or {}

    allowed_tools = {str(v) for v in (permissions.get("allowed_tools") or [])}
    requested_tools = {str(v) for v in (slot.get("allowed_tools") or [])}
    if requested_tools - allowed_tools:
        raise PermissionError(f"Agent lacks requested tools: {sorted(requested_tools - allowed_tools)}")

    network = str(slot.get("network_policy") or "project_policy")
    agent_network = str(permissions.get("network_policy") or "deny_unless_required")
    requested_hosts = {str(v).lower() for v in (slot.get("network_allowlist") or [])}
    allowed_hosts = {str(v).lower() for v in (permissions.get("network_allowlist") or [])}
    if network not in {"none", "deny", "project_policy"} and agent_network in {"none", "deny", "deny_unless_required"}:
        raise PermissionError("Slot requests network access not authorized by the agent permission profile.")
    if requested_hosts and "*" not in allowed_hosts and not requested_hosts.issubset(allowed_hosts):
        raise PermissionError(f"Agent lacks requested network destinations: {sorted(requested_hosts - allowed_hosts)}")

    _enforce_scope_subset("PM scope", slot.get("pm_scope"), permissions.get("pm_scope"))
    _enforce_scope_subset("secret scope", slot.get("secret_scope"), permissions.get("secret_scope"))
    _enforce_scope_subset("deployment scope", slot.get("deployment_scope"), permissions.get("deployment_scope"))


def verify_fencing(expected_epoch: int, expected_token: str, actor_agent_id: str | None = None) -> dict[str, Any]:
    state, supervisor = live_supervisor()
    if int(state.get("coordination_epoch") or 0) != int(expected_epoch):
        raise PermissionError("Coordination epoch is stale.")
    if str(supervisor.get("fencing_token") or "") != str(expected_token):
        raise PermissionError("Supervisor fencing token is stale or invalid.")
    if actor_agent_id and str(supervisor.get("agent_id")) != str(actor_agent_id):
        raise PermissionError("Shared coordination mutation actor is not the active Supervisor.")
    return state


def validate_handoff(slot: dict[str, Any]) -> None:
    required = [
        "id", "work_unit_id", "base_sha", "required_roles", "required_capabilities", "allowed_paths",
        "denied_paths", "allowed_tools", "network_policy", "network_allowlist", "pm_scope", "secret_scope",
        "deployment_scope", "acceptance_criteria", "required_checks", "risk_classification"
    ]
    must_be_nonempty = {"id", "work_unit_id", "base_sha", "required_roles", "allowed_paths", "acceptance_criteria", "required_checks", "risk_classification"}
    missing = [key for key in required if slot.get(key) is None or (key in must_be_nonempty and slot.get(key) in ("", []))]
    if missing:
        raise ValueError(f"Slot handoff envelope missing required field(s): {', '.join(missing)}")


if __name__ == "__main__":
    print("ANPOS guard library. Import from coordination scripts; it is not a standalone authority service.")
