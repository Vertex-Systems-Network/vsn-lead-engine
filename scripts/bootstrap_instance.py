#!/usr/bin/env python3
"""Initialize a child repository created from the ANPOS template.

The canonical source remains inert. Child bootstrap resets inherited runtime
identity/state, activates repository-local policy, installs universally safe
runtime blueprints and records feature-dependent quality checks for capability
resolution. It does not connect PM providers, attach AIs, apply GitHub admin
rules, configure production credentials, or invent platform capabilities.

Dry-run by default. Use --apply to write changes. The source repository is
protected unless --allow-source is deliberately supplied for tests.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPO = "Vertex-Systems-Network/ai-native-project-operating-system"
BLUEPRINT_ROOT = ROOT / "blueprints" / "github"

ALWAYS_INSTALL_WORKFLOWS = (
    "repository-quality.yml",
    "technology-update-watch.yml",
    "innovation-scout.yml",
    "protocol-update-watch.yml",
)
SECURITY_CAPABILITY_WORKFLOWS = (
    "codeql-actions.yml",
    "dependency-review.yml",
    "scorecard.yml",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def infer_repository() -> str | None:
    env = os.getenv("GITHUB_REPOSITORY")
    if env:
        return env
    try:
        remote = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return None
    remote = remote.removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    marker = "github.com/"
    if marker in remote:
        return remote.split(marker, 1)[1]
    return None


def add_workflow(changed: dict[str, str], filename: str) -> None:
    source = BLUEPRINT_ROOT / "workflows" / filename
    if not source.exists():
        raise RuntimeError(f"Missing required child workflow blueprint: {source}")
    changed[f".github/workflows/{filename}"] = source.read_text(encoding="utf-8")


def add_runtime_blueprints(changed: dict[str, str], security_capability: str) -> list[str]:
    installed: list[str] = []
    for filename in ALWAYS_INSTALL_WORKFLOWS:
        add_workflow(changed, filename)
        installed.append(filename)
    if security_capability == "enabled":
        for filename in SECURITY_CAPABILITY_WORKFLOWS:
            add_workflow(changed, filename)
            installed.append(filename)
    dependabot = BLUEPRINT_ROOT / "dependabot.yml"
    if not dependabot.exists():
        raise RuntimeError(f"Missing required child Dependabot blueprint: {dependabot}")
    changed[".github/dependabot.yml"] = dependabot.read_text(encoding="utf-8")
    installed.append("dependabot.yml")
    return installed


def child_policy(path: str, status: str = "active_policy") -> str:
    doc = load(path)
    doc["status"] = status
    doc["activation_scope"] = "child_project"
    return json.dumps(doc, indent=2) + "\n"


def reset_runtime(repository: str, project_name: str, owner: str, security_capability: str) -> dict[str, str]:
    timestamp = now()
    changed: dict[str, str] = {}

    protocol = load("config/protocol/version.json")
    instance = load("config/protocol/instance.json")
    instance.update({
        "instance_status": "active_project",
        "instance_id": str(uuid.uuid4()),
        "project_name": project_name,
        "repository": repository,
        "repository_owner": repository.split("/", 1)[0],
        "initialized_at": timestamp,
        "initialized_by": owner,
        "source_protocol_version": protocol.get("version"),
        "bootstrap_completed": True,
    })
    changed["config/protocol/instance.json"] = json.dumps(instance, indent=2) + "\n"

    state = load("config/ai/project-state.json")
    state.update({
        "lifecycle_stage": "not_started", "current_phase": None, "current_module": None,
        "current_work_unit": None, "last_verified_completion": None, "next_valid_work_unit": None,
        "outstanding_updates": [], "outstanding_removals": [],
        "unresolved_decisions": [
            "Choose a Project Management System or explicitly skip PM integration.",
            "Choose and identity-verify the Development AI agent pool available in the current host.",
            "Ask the user whether to apply the recommended GitHub Rules policy.",
            "Resolve capability-dependent GitHub security checks before making them required."
        ],
        "critical_defects": [], "last_reconciled_repository_ref": None, "last_reconciled_at": None,
    })
    if isinstance(state.get("progress"), dict):
        for key in state["progress"]:
            state["progress"][key] = 0
    changed["config/ai/project-state.json"] = json.dumps(state, indent=2) + "\n"

    memory = load("config/ai/memory-provenance.json")
    memory["entries"] = []
    changed["config/ai/memory-provenance.json"] = json.dumps(memory, indent=2) + "\n"

    queue = load("config/coordination/agent-work-queue.json")
    queue["slots"] = []
    queue["updated_at"] = timestamp
    changed["config/coordination/agent-work-queue.json"] = json.dumps(queue, indent=2) + "\n"

    supervisor = load("config/coordination/supervisor-state.json")
    supervisor.update({
        "coordination_epoch": 0, "merge_generation": 0, "last_merge_sha": None, "last_merge_at": None,
        "active_worker_count": 0, "open_required_action_alert_count": 0, "last_pm_sync_at": None,
        "last_readme_dashboard_update_at": None, "last_reconciled_main_sha": None, "status": "unassigned",
    })
    supervisor["supervisor"] = {
        "status": "unassigned", "agent_id": None, "agent_type": None, "identity_ref": None,
        "branch": None, "active_module_id": None, "active_work_unit_id": None,
        "started_at": None, "heartbeat_at": None, "lease_id": None, "lease_status": "not_acquired",
        "lease_expires_at": None, "fencing_token": None, "election_ref": None,
    }
    changed["config/coordination/supervisor-state.json"] = json.dumps(supervisor, indent=2) + "\n"

    for path, list_key in [
        ("config/coordination/merge-events.json", "events"),
        ("config/coordination/agent-alerts.json", "alerts"),
        ("config/consent/consent-requests.json", "requests"),
    ]:
        doc = load(path)
        doc[list_key] = []
        if "next_sequence" in doc:
            doc["next_sequence"] = 1
        changed[path] = json.dumps(doc, indent=2) + "\n"

    pm = load("config/integrations/project-management.json")
    pm["status"] = "selection_required"
    pm["activation_scope"] = "child_project"
    pm["selection"] = {
        "status": "not_selected", "selected_provider_id": None, "selected_provider_name": None,
        "workspace_or_org_id": None, "workspace_or_org_name": None, "external_project_id": None,
        "external_project_name": None, "external_project_url": None, "connected_at": None,
        "verified_at": None, "sync_enabled": False,
    }
    changed["config/integrations/project-management.json"] = json.dumps(pm, indent=2) + "\n"

    linear = load("config/integrations/linear-sync.json")
    linear["status"] = "not_selected"
    linear["enabled"] = False
    linear["activation_scope"] = "child_project_only_when_selected"
    linear["project"] = {"name": None, "id": None, "url": None}
    for key in ["last_successful_sync_at", "last_attempt_at", "last_error", "last_reconciled_main_sha", "last_linear_status_update_id"]:
        if key in linear:
            linear[key] = None
    linear["sync_result"] = "provider_not_selected"
    changed["config/integrations/linear-sync.json"] = json.dumps(linear, indent=2) + "\n"

    agents = load("config/ai/agent-catalog.json")
    agents["selection_status"] = "discovery_required"
    agents["available_agents"] = []
    agents["selected_agents"] = []
    agents["suggested_but_unavailable"] = []
    agents["role_assignments"] = {"supervisor_agent_id": None, "worker_agent_ids": []}
    changed["config/ai/agent-catalog.json"] = json.dumps(agents, indent=2) + "\n"

    installed = add_runtime_blueprints(changed, security_capability)
    quality = load("config/quality/quality-policy.json")
    quality["status"] = "installed_pending_verification"
    quality["activation_scope"] = "child_project"
    quality["setup_state"] = {
        "baseline_files_installed_by_bootstrap": True, "installed_blueprints": installed,
        "baseline_verification": "pending_first_child_run", "github_security_capability": security_capability,
        "capability_dependent_workflows": list(SECURITY_CAPABILITY_WORKFLOWS),
        "capability_resolution": "resolved" if security_capability in {"enabled", "unavailable"} else "pending_runtime_detection",
        "stack_specific_tooling": "awaiting_technology_approval",
    }
    changed["config/quality/quality-policy.json"] = json.dumps(quality, indent=2) + "\n"

    rules = load("config/github/ruleset-policy.json")
    rules["status"] = "pending_user_decision"
    rules["activation_scope"] = "child_project"
    rules["setup_state"] = {
        "user_decision": None, "application_status": "not_applied", "enforcement_verified": False,
        "governance_audit_installed": False,
    }
    changed["config/github/ruleset-policy.json"] = json.dumps(rules, indent=2) + "\n"

    # Child-local policies activate without inventing external connections, credentials, releases or approvals.
    changed["config/security/control-plane-policy.json"] = child_policy("config/security/control-plane-policy.json")
    changed["config/security/trust-policy.json"] = child_policy("config/security/trust-policy.json")
    changed["config/security/threat-model.json"] = child_policy("config/security/threat-model.json", "pending_project_threat_model")
    changed["config/runtime/budgets.json"] = child_policy("config/runtime/budgets.json", "active_guardrails")
    changed["config/release/release-policy.json"] = child_policy("config/release/release-policy.json", "pending_environment_configuration")
    changed["config/data/data-governance.json"] = child_policy("config/data/data-governance.json", "pending_project_data_classification")
    changed["config/operations/operations-policy.json"] = child_policy("config/operations/operations-policy.json", "pending_operational_configuration")
    changed["config/contracts/migration-policy.json"] = child_policy("config/contracts/migration-policy.json")
    changed["config/integrations/sync-authority.json"] = child_policy("config/integrations/sync-authority.json")
    changed["config/design/design-assurance.json"] = child_policy("config/design/design-assurance.json", "pending_design_decision")
    changed["config/testing/conformance-scenarios.json"] = child_policy("config/testing/conformance-scenarios.json", "required_for_runtime_certification")

    assurance_state = load("config/assurance/assurance-state.json")
    assurance_state["status"] = "pending_assurance_classification"
    assurance_state["activation_scope"] = "child_project"
    assurance_state["last_reconciled_at"] = None
    assurance_state["last_reconciled_ref"] = None
    for row in assurance_state.get("requirements", []):
        if isinstance(row, dict):
            row["evidence_refs"] = []
            row["last_verified_ref"] = None
            row["last_verified_at"] = None
            row["blocking_findings"] = []
            if row.get("requirement_id") != "REQ-86":
                row["state"] = "not_started"
    changed["config/assurance/assurance-state.json"] = json.dumps(assurance_state, indent=2) + "\n"

    evidence = load("config/research/evidence-registry.json")
    evidence["status"] = "active_registry"
    evidence["activation_scope"] = "child_project"
    evidence["entries"] = []
    changed["config/research/evidence-registry.json"] = json.dumps(evidence, indent=2) + "\n"

    changed["config/assurance/runtime-executors.json"] = child_policy("config/assurance/runtime-executors.json", "executor_contract")
    changed["config/ai/ai-evaluation-policy.json"] = child_policy("config/ai/ai-evaluation-policy.json", "pending_capability_detection")
    changed["config/product/product-validation.json"] = child_policy("config/product/product-validation.json", "pending_applicability_detection")
    changed["config/product/product-analytics.json"] = child_policy("config/product/product-analytics.json", "pending_applicability_detection")
    changed["config/product/experimentation-policy.json"] = child_policy("config/product/experimentation-policy.json", "optional_inactive")
    changed["config/release/progressive-delivery.json"] = child_policy("config/release/progressive-delivery.json", "pending_applicability_detection")
    changed["config/quality/engineering-review-policy.json"] = child_policy("config/quality/engineering-review-policy.json", "required_for_major_module_or_release_review")
    changed["config/ai/responsible-ai-policy.json"] = child_policy("config/ai/responsible-ai-policy.json", "pending_high_impact_ai_detection")
    changed["config/compliance/compliance-profile.json"] = child_policy("config/compliance/compliance-profile.json", "pending_applicability_detection")
    changed["config/contracts/deprecation-policy.json"] = child_policy("config/contracts/deprecation-policy.json", "pending_applicability_detection")

    decisions = load("config/architecture/decision-records.json")
    decisions["status"] = "active_registry"
    decisions["activation_scope"] = "child_project"
    decisions["decisions"] = []
    changed["config/architecture/decision-records.json"] = json.dumps(decisions, indent=2) + "\n"

    assets = load("config/ai/asset-registry.json")
    assets["status"] = "pending_ai_asset_detection"
    assets["activation_scope"] = "child_project"
    assets["assets"] = []
    changed["config/ai/asset-registry.json"] = json.dumps(assets, indent=2) + "\n"

    runbooks = load("config/operations/runbooks-and-drills.json")
    runbooks["status"] = "pending_operational_applicability"
    runbooks["activation_scope"] = "child_project"
    runbooks["runbooks"] = []
    runbooks["drills"] = []
    changed["config/operations/runbooks-and-drills.json"] = json.dumps(runbooks, indent=2) + "\n"

    audit = load("config/audit/audit-journal.json")
    audit["status"] = "active_journal"
    audit["activation_scope"] = "child_project"
    audit["entries"] = []
    audit["integrity"] = {"mode": "sha256_hash_chain", "genesis_hash": None, "latest_entry_hash": None, "last_verified_at": None}
    changed["config/audit/audit-journal.json"] = json.dumps(audit, indent=2) + "\n"

    risks = load("config/risk/risk-register.json")
    risks["status"] = "active_registry"
    risks["activation_scope"] = "child_project"
    risks["risks"] = []
    changed["config/risk/risk-register.json"] = json.dumps(risks, indent=2) + "\n"

    handle = owner.lstrip("@")
    protected = [
        "/.gitignore", "/AGENTS.md", "/.ai/", "/CLAUDE.md", "/GEMINI.md", "/.cursor/", "/.windsurf/", "/.github/", "/blueprints/",
        "/START-HERE.md", "/PROJECT-INITIALIZATION.md", "/PROJECT-MANAGEMENT.md", "/AI-NATIVE-EXECUTION.md",
        "/MULTI-AGENT-ORCHESTRATION.md", "/AUTO-AGENT.md", "/SUPERVISOR.md", "/ORCHESTRATOR.md",
        "/DEVELOPMENT-LIFECYCLE.md", "/CONTINUOUS-IMPROVEMENT.md", "/GITHUB-GOVERNANCE.md", "/CODE-QUALITY.md",
        "/SECURITY.md", "/CONTROL-PLANE-SECURITY.md", "/PRODUCTION-ASSURANCE.md", "/DESIGN-DATA-OPERATIONS.md", "/AI-NATIVE-PRODUCT-ASSURANCE.md", "/AI-NATIVE-GOVERNANCE-ASSURANCE.md",
        "/config/ai/agent-catalog.json", "/config/ai/memory-provenance.json", "/config/ai/ai-evaluation-policy.json", "/config/ai/responsible-ai-policy.json", "/config/ai/asset-registry.json", "/config/coordination/", "/config/protocol/",
        "/config/security/", "/config/consent/", "/config/github/", "/config/quality/", "/config/runtime/", "/config/release/",
        "/config/data/", "/config/product/", "/config/assurance/", "/config/research/", "/config/compliance/", "/config/architecture/", "/config/audit/", "/config/risk/", "/config/operations/", "/config/contracts/", "/config/integrations/", "/config/design/", "/config/testing/",
        "/config/traceability/", "/schemas/", "/scripts/", "/tests/", "/requirements-anpos.txt",
    ]
    codeowners = [f"# Generated by scripts/bootstrap_instance.py for {repository}", f"* @{handle}"]
    codeowners.extend(f"{path} @{handle}" for path in protected)
    changed[".github/CODEOWNERS"] = "\n".join(codeowners) + "\n"
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-source", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--project-name")
    parser.add_argument("--github-owner", help="Authorized GitHub user/team handle used to render child CODEOWNERS")
    parser.add_argument(
        "--github-security-capability", choices=["auto", "enabled", "unavailable"], default="auto",
        help="Whether capability-dependent GitHub security workflows are supported. auto records pending detection instead of guessing.",
    )
    args = parser.parse_args()

    repository = args.repository or infer_repository()
    if not repository or "/" not in repository:
        raise SystemExit("Unable to determine owner/repository. Pass --repository owner/name.")
    if repository == SOURCE_REPO and not args.allow_source:
        raise SystemExit("Refusing to bootstrap the template source repository. Use --allow-source only for deliberate testing.")
    if args.apply and not args.github_owner:
        raise SystemExit("--github-owner is required with --apply so a child repository cannot inherit source CODEOWNERS identity.")

    capability = args.github_security_capability
    if capability == "auto":
        env = str(os.getenv("ANPOS_GITHUB_SECURITY_CAPABLE") or "").strip().lower()
        capability = "enabled" if env in {"1", "true", "yes"} else "unavailable" if env in {"0", "false", "no"} else "unknown"

    project_name = args.project_name or repository.split("/", 1)[1].replace("-", " ").strip().title()
    preview_owner = args.github_owner or "REQUIRED-ON-APPLY"
    changes = reset_runtime(repository, project_name, preview_owner, capability)

    if not args.apply:
        print("DRY RUN - no files written")
        print("Would initialize child project:", repository)
        print("GitHub security capability:", capability)
        if not args.github_owner:
            print("NOTE: --github-owner is required when --apply is used.")
        print("NOTE: PM and Development AI selections remain unresolved until the user selects/connects them.")
        print("NOTE: Only universally safe quality/runtime blueprints install before capability verification.")
        print("NOTE: GitHub Rules remain unapplied until user approval and capability/check verification.")
        for path in sorted(changes):
            print("-", path)
        return 0

    for relative, content in changes.items():
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"Initialized ANPOS child project {repository} with {len(changes)} reset/generated files.")
    print("NEXT: resolve PM/AI identity selection, detect optional GitHub security capabilities, verify quality, then decide GitHub Rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
