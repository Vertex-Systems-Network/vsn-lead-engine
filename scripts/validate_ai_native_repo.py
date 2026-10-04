#!/usr/bin/env python3
"""Validate ANPOS protocol, security, coordination and assurance invariants."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

try:
    from jsonschema import Draft202012Validator
except Exception:
    Draft202012Validator = None

ACTIVE_SLOT_STATES = {
    "claimed", "in_progress", "blocked", "submitted_for_review", "changes_requested", "approved"
}
LEASE_STATES = {"not_acquired", "active", "expired", "released", "revoked", "orphaned", "recovered"}
REQUIRED_CONFORMANCE = {
    "two_workers_same_slot",
    "unauthorized_worker_restricted_slot",
    "missing_required_capability",
    "path_permission_violation",
    "stale_fencing_token",
    "orphan_claim_ref",
    "supervisor_crash_failover",
    "merge_during_worker_execution",
    "duplicate_event_replay",
    "pm_provider_outage_or_switch",
    "malicious_external_instruction",
    "consent_expiry_replay_or_hash_mismatch",
    "control_plane_validator_tampering",
    "agent_budget_retry_loop",
    "selected_agent_unavailable_or_identity_expired",
    "tool_network_pm_or_secret_scope_escalation",
    "pm_sync_conflict_or_echo_loop",
    "release_missing_required_evidence",
    "approved_design_revision_drift",
    "destructive_migration_without_valid_consent",
    "backup_restore_or_recovery_verification_failure",
    "ai_configuration_changed_without_required_reevaluation",
    "product_success_claim_without_verified_outcome_evidence",
    "unsafe_or_unbounded_experiment",
    "progressive_rollout_health_guardrail_failure",
    "stale_feature_flag_without_owner_or_review_date",
    "critical_engineering_review_finding",
    "high_impact_ai_without_required_human_oversight",
    "regulated_or_sensitive_processing_without_required_compliance_evidence",
    "accepted_architecture_decision_silently_reversed",
    "ai_asset_configuration_drift_after_certified_evaluation",
    "deprecated_contract_removed_before_approved_support_window",
    "critical_recovery_runbook_or_resilience_drill_failure",
    "audit_journal_integrity_chain_break",
    "expired_risk_acceptance_used_to_bypass_gate",
}
PROTECTED_PATTERNS = {
    "/.gitignore", "/AGENTS.md", "/.ai/**", "/.github/**", "/blueprints/**", "/START-HERE.md",
    "/PROJECT-INITIALIZATION.md", "/PROJECT-MANAGEMENT.md", "/AI-NATIVE-EXECUTION.md",
    "/MULTI-AGENT-ORCHESTRATION.md", "/AUTO-AGENT.md", "/SUPERVISOR.md", "/ORCHESTRATOR.md",
    "/DEVELOPMENT-LIFECYCLE.md", "/CONTINUOUS-IMPROVEMENT.md", "/GITHUB-GOVERNANCE.md",
    "/CODE-QUALITY.md", "/SECURITY.md", "/CONTROL-PLANE-SECURITY.md", "/PRODUCTION-ASSURANCE.md",
    "/DESIGN-DATA-OPERATIONS.md", "/AI-NATIVE-PRODUCT-ASSURANCE.md", "/AI-NATIVE-GOVERNANCE-ASSURANCE.md", "/config/ai/agent-catalog.json", "/config/ai/memory-provenance.json",
    "/config/ai/ai-evaluation-policy.json", "/config/ai/responsible-ai-policy.json", "/config/ai/asset-registry.json",
    "/config/coordination/**", "/config/protocol/**", "/config/security/**", "/config/consent/**",
    "/config/github/**", "/config/quality/**", "/config/runtime/**", "/config/release/**",
    "/config/data/**", "/config/product/**", "/config/operations/**", "/config/contracts/**", "/config/integrations/**",
    "/config/design/**", "/config/testing/**", "/config/traceability/**", "/config/assurance/**", "/config/research/**", "/config/compliance/**", "/config/architecture/**", "/config/audit/**", "/config/risk/**", "/schemas/**", "/scripts/**",
    "/tests/**", "/requirements-anpos.txt",
}


def fail(message: str) -> None:
    ERRORS.append(message)


def load_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"{relative}: invalid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        fail(f"{relative}: top-level JSON value must be an object")
        return {}
    return data


def ids(items: Any, label: str) -> set[str]:
    found: set[str] = set()
    if items is None:
        return found
    if not isinstance(items, list):
        fail(f"{label}: expected a list")
        return found
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"{label}[{index}]: expected an object")
            continue
        value = item.get("id")
        if not isinstance(value, str) or not value.strip():
            fail(f"{label}[{index}]: missing non-empty id")
            continue
        if value in found:
            fail(f"{label}: duplicate id {value}")
        found.add(value)
    return found


def check_refs(values: Any, valid: set[str], label: str) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        fail(f"{label}: expected a list")
        return
    for value in values:
        if not isinstance(value, str):
            fail(f"{label}: reference must be a string")
        elif value and value not in valid:
            fail(f"{label}: unknown reference {value}")


def require_true(doc: dict[str, Any], path: list[str], label: str) -> None:
    current: Any = doc
    for key in path:
        if not isinstance(current, dict):
            fail(f"{label}: missing {'.'.join(path)}")
            return
        current = current.get(key)
    if current is not True:
        fail(f"{label}: {'.'.join(path)} must be true")


def validate_required_files() -> None:
    # Active child repositories intentionally exclude vendor-only Repository Supervisor assets.
    required = [
        ".gitignore", "AGENTS.md", ".ai/manifest.json", "PROJECT-INITIALIZATION.md", "PROJECT-MANAGEMENT.md", "START-HERE.md",
        "AI-NATIVE-EXECUTION.md", "MULTI-AGENT-ORCHESTRATION.md", "AUTO-AGENT.md", "SUPERVISOR.md", "ORCHESTRATOR.md",
        "DEVELOPMENT-LIFECYCLE.md", "CONTINUOUS-IMPROVEMENT.md", "GITHUB-GOVERNANCE.md", "CODE-QUALITY.md", "SECURITY.md",
        "CONTROL-PLANE-SECURITY.md", "PRODUCTION-ASSURANCE.md", "DESIGN-DATA-OPERATIONS.md", "AI-NATIVE-PRODUCT-ASSURANCE.md", "AI-NATIVE-GOVERNANCE-ASSURANCE.md", "README.md",
        "PROJECT-IDEA.md", "requirements-anpos.txt",
        "config/protocol/version.json", "config/protocol/instance.json", "config/protocol/migrations.json", "config/protocol/state-machine.json",
        "config/protocol/blueprint-completion.json", "config/protocol/extension-contract.json",
        "config/traceability/requirements-traceability.json", "config/integrations/project-management.json",
        "config/integrations/linear-sync.json", "config/integrations/sync-authority.json", "config/ai/agent-catalog.json",
        "config/ai/memory-provenance.json", "config/ai/ai-evaluation-policy.json", "config/ai/responsible-ai-policy.json", "config/ai/asset-registry.json", "config/github/ruleset-policy.json", "config/github/path-ownership.json",
        "config/quality/quality-policy.json", "config/security/control-plane-policy.json", "config/security/trust-policy.json",
        "config/security/threat-model.json", "config/runtime/budgets.json", "config/runtime/execution-sandbox.json", "config/release/release-policy.json", "config/release/progressive-delivery.json",
        "config/data/data-governance.json", "config/product/product-validation.json", "config/product/product-analytics.json",
        "config/product/experimentation-policy.json", "config/quality/engineering-review-policy.json", "config/operations/operations-policy.json", "config/operations/runbooks-and-drills.json", "config/contracts/migration-policy.json", "config/contracts/deprecation-policy.json",
        "config/design/design-intake.json", "config/design/design-assurance.json", "config/testing/conformance-scenarios.json",
        "config/testing/reference-e2e-matrix.json",
        "config/assurance/assurance-state.json", "config/assurance/runtime-executors.json", "config/research/evidence-registry.json",
        "config/compliance/compliance-profile.json", "config/architecture/decision-records.json", "config/audit/audit-journal.json", "config/risk/risk-register.json",
        "config/consent/consent-requests.json", "config/coordination/agent-work-queue.json",
        "config/coordination/supervisor-state.json", ".github/CODEOWNERS",
        "schemas/config-base.schema.json", "schemas/project-state.schema.json", "schemas/agent-work-queue.schema.json",
        "schemas/supervisor-state.schema.json", "schemas/agent-catalog.schema.json", "schemas/consent-requests.schema.json",
        "schemas/design-intake.schema.json", "schemas/requirements-traceability.schema.json",
        "schemas/assurance-state.schema.json", "schemas/research-evidence.schema.json", "schemas/runtime-executors.schema.json",
        "schemas/ai-evaluation-policy.schema.json", "schemas/product-validation.schema.json", "schemas/product-analytics.schema.json",
        "schemas/experimentation-policy.schema.json", "schemas/progressive-delivery.schema.json", "schemas/engineering-review-policy.schema.json",
        "schemas/responsible-ai-policy.schema.json", "schemas/compliance-profile.schema.json", "schemas/decision-records.schema.json",
        "schemas/ai-asset-registry.schema.json", "schemas/deprecation-policy.schema.json", "schemas/runbooks-and-drills.schema.json",
        "schemas/audit-journal.schema.json", "schemas/risk-register.schema.json",
        "schemas/blueprint-completion.schema.json", "schemas/reference-e2e-matrix.schema.json", "schemas/extension-contract.schema.json", "schemas/execution-sandbox.schema.json",
        "scripts/bootstrap_instance.py", "scripts/anpos_guard.py", "scripts/claim_slot.py", "scripts/supervisor_lease.py",
        "scripts/lease_control.py", "scripts/coordination_mutation.py", "scripts/consent_guard.py",
        "scripts/install_quality_capabilities.py", "scripts/configure_dependabot.py", "scripts/validate_ai_native_repo.py",
        "tests/test_control_plane.py", "tests/test_product_assurance.py", "tests/test_governance_assurance.py", "tests/test_blueprint_closure.py", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
        "blueprints/github/dependabot.yml", "blueprints/github/workflows/codeql-actions.yml",
        "blueprints/github/workflows/dependency-review.yml", "blueprints/github/workflows/governance-audit.yml",
        "blueprints/github/workflows/innovation-scout.yml", "blueprints/github/workflows/protocol-update-watch.yml",
        "blueprints/github/workflows/repository-quality.yml", "blueprints/github/workflows/scorecard.yml",
        "blueprints/github/workflows/technology-update-watch.yml",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"missing required protocol/blueprint file: {relative}")


def validate_json_schemas() -> None:
    if Draft202012Validator is None:
        fail("jsonschema dependency missing; install requirements-anpos.txt before repository validation")
        return
    base = load_json("schemas/config-base.schema.json")
    try:
        Draft202012Validator.check_schema(base)
    except Exception as exc:
        fail(f"schemas/config-base.schema.json: invalid schema: {exc}")
        return

    for base_dir in [ROOT / "config", ROOT / ".ai"]:
        for path in sorted(base_dir.rglob("*.json")) if base_dir.exists() else []:
            relative = path.relative_to(ROOT).as_posix()
            if relative == "config/runtime.json":
                continue  # VSN Lead Engine application runtime configuration, not ANPOS machine state.
            instance = load_json(relative)
            if instance:
                for error in Draft202012Validator(base).iter_errors(instance):
                    fail(f"{relative}: base schema violation: {error.message}")

    mapping = {
        "config/ai/project-state.json": "schemas/project-state.schema.json",
        "config/coordination/agent-work-queue.json": "schemas/agent-work-queue.schema.json",
        "config/coordination/supervisor-state.json": "schemas/supervisor-state.schema.json",
        "config/ai/agent-catalog.json": "schemas/agent-catalog.schema.json",
        "config/consent/consent-requests.json": "schemas/consent-requests.schema.json",
        "config/design/design-intake.json": "schemas/design-intake.schema.json",
        "config/traceability/requirements-traceability.json": "schemas/requirements-traceability.schema.json",
        "config/assurance/assurance-state.json": "schemas/assurance-state.schema.json",
        "config/research/evidence-registry.json": "schemas/research-evidence.schema.json",
        "config/assurance/runtime-executors.json": "schemas/runtime-executors.schema.json",
        "config/ai/ai-evaluation-policy.json": "schemas/ai-evaluation-policy.schema.json",
        "config/product/product-validation.json": "schemas/product-validation.schema.json",
        "config/product/product-analytics.json": "schemas/product-analytics.schema.json",
        "config/product/experimentation-policy.json": "schemas/experimentation-policy.schema.json",
        "config/release/progressive-delivery.json": "schemas/progressive-delivery.schema.json",
        "config/quality/engineering-review-policy.json": "schemas/engineering-review-policy.schema.json",
        "config/ai/responsible-ai-policy.json": "schemas/responsible-ai-policy.schema.json",
        "config/compliance/compliance-profile.json": "schemas/compliance-profile.schema.json",
        "config/architecture/decision-records.json": "schemas/decision-records.schema.json",
        "config/ai/asset-registry.json": "schemas/ai-asset-registry.schema.json",
        "config/contracts/deprecation-policy.json": "schemas/deprecation-policy.schema.json",
        "config/operations/runbooks-and-drills.json": "schemas/runbooks-and-drills.schema.json",
        "config/audit/audit-journal.json": "schemas/audit-journal.schema.json",
        "config/risk/risk-register.json": "schemas/risk-register.schema.json",
        "config/protocol/blueprint-completion.json": "schemas/blueprint-completion.schema.json",
        "config/testing/reference-e2e-matrix.json": "schemas/reference-e2e-matrix.schema.json",
        "config/protocol/extension-contract.json": "schemas/extension-contract.schema.json",
        "config/runtime/execution-sandbox.json": "schemas/execution-sandbox.schema.json",
    }
    for instance_path, schema_path in mapping.items():
        schema = load_json(schema_path)
        instance = load_json(instance_path)
        try:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
                location = "/".join(str(v) for v in error.absolute_path) or "<root>"
                fail(f"{instance_path} [{location}]: {error.message}")
        except Exception as exc:
            fail(f"{schema_path}: schema validation failure: {exc}")


def validate_manifest() -> None:
    doc = load_json(".ai/manifest.json")
    paths = list(doc.get("common", []))
    roles = doc.get("roles", {})
    if not isinstance(roles, dict):
        fail(".ai/manifest.json: roles must be an object")
        return
    for role, files in roles.items():
        if not isinstance(files, list):
            fail(f"manifest role {role}: expected file list")
            continue
        paths.extend(files)
    for relative in paths:
        if not isinstance(relative, str) or not (ROOT / relative).exists():
            fail(f"manifest references missing path: {relative}")

    common = set(doc.get("common", []))
    if not {"config/security/trust-policy.json", "config/runtime/budgets.json"}.issubset(common):
        fail("manifest common context must include trust policy and runtime budgets")
    for role, required in {
        "worker": {"CONTROL-PLANE-SECURITY.md", "config/ai/agent-catalog.json"},
        "supervisor": {"CONTROL-PLANE-SECURITY.md", "PRODUCTION-ASSURANCE.md", "DESIGN-DATA-OPERATIONS.md"},
        "security": {"CONTROL-PLANE-SECURITY.md", "config/security/threat-model.json"},
        "release_ops": {"PRODUCTION-ASSURANCE.md", "config/release/release-policy.json", "config/operations/operations-policy.json"},
    }.items():
        actual = set(roles.get(role, []))
        if not required.issubset(actual):
            fail(f"manifest role {role} missing hardening context: {sorted(required - actual)}")


def validate_protocol_versioning() -> None:
    version = load_json("config/protocol/version.json")
    instance = load_json("config/protocol/instance.json")
    migrations = load_json("config/protocol/migrations.json")
    current = version.get("version")
    if not isinstance(current, str) or not re.fullmatch(r"\d+\.\d+\.\d+", current):
        fail("protocol version must be numeric semantic major.minor.patch")
        return
    if migrations.get("current_protocol_version") != current:
        fail("protocol version: migrations.current_protocol_version must match version.json")
    if instance.get("instance_status") == "template_source" and instance.get("source_protocol_version") != current:
        fail("protocol version: template source instance.source_protocol_version must match version.json")
    last = version.get("last_protocol_migration")
    applied = migrations.get("applied_migrations", [])
    if last and not any(
        isinstance(record, dict)
        and record.get("id") == last
        and record.get("status") == "applied"
        and record.get("to_version") == current
        for record in applied if isinstance(applied, list)
    ):
        fail("last_protocol_migration must reference an applied migration to the current version")


def validate_template_boundary() -> None:
    instance = load_json("config/protocol/instance.json")
    if instance.get("instance_status") != "template_source":
        return

    pm = load_json("config/integrations/project-management.json")
    linear = load_json("config/integrations/linear-sync.json")
    agents = load_json("config/ai/agent-catalog.json")
    rules = load_json("config/github/ruleset-policy.json")
    quality = load_json("config/quality/quality-policy.json")
    supervisor = load_json("config/coordination/supervisor-state.json")
    queue = load_json("config/coordination/agent-work-queue.json")
    memory = load_json("config/ai/memory-provenance.json")
    consent = load_json("config/consent/consent-requests.json")
    design = load_json("config/design/design-intake.json")

    selection = pm.get("selection") or {}
    if pm.get("status") != "template_blueprint" or pm.get("activation_scope") != "child_project_only":
        fail("template source: PM provider state must remain template_blueprint/child_project_only")
    if selection.get("status") != "not_selected" or selection.get("sync_enabled") is not False:
        fail("template source: PM provider must remain unselected and unsynchronized")
    for key in (
        "selected_provider_id", "selected_provider_name", "workspace_or_org_id", "workspace_or_org_name",
        "external_project_id", "external_project_name", "external_project_url", "connected_at", "verified_at"
    ):
        if selection.get(key) not in (None, ""):
            fail(f"template source: PM runtime field {key} must be empty")

    if linear.get("enabled") is not False or any((linear.get("project") or {}).get(k) not in (None, "") for k in ("name", "id", "url")):
        fail("template source: Linear adapter must remain disabled/unmapped")
    for key in ("last_successful_sync_at", "last_attempt_at", "last_reconciled_main_sha", "last_linear_status_update_id"):
        if linear.get(key) not in (None, ""):
            fail(f"template source: Linear runtime field {key} must be empty")

    if agents.get("available_agents") or agents.get("selected_agents"):
        fail("template source: project-specific AI agent pool must be empty")
    assignments = agents.get("role_assignments") or {}
    if assignments.get("supervisor_agent_id") not in (None, "") or assignments.get("worker_agent_ids"):
        fail("template source: AI role assignments must remain empty")

    sup = supervisor.get("supervisor") or {}
    if supervisor.get("last_pm_sync_at") not in (None, "") or sup.get("status") != "unassigned" or sup.get("lease_status") != "not_acquired":
        fail("template source: Supervisor runtime must remain unassigned/unleased/unmapped")
    if queue.get("slots"):
        fail("template source: work queue must not contain child runtime slots")
    if memory.get("entries"):
        fail("template source: project memory provenance entries must remain empty")
    if consent.get("requests"):
        fail("template source: project consent requests must remain empty")
    if design.get("source_url") not in (None, "") or design.get("approval_status") != "not_approved":
        fail("template source: no project-specific design may be attached/approved")

    if rules.get("status") != "template_blueprint" or rules.get("activation_scope") != "child_project_only":
        fail("template source: GitHub Rules must remain child-project blueprint")
    if quality.get("status") != "template_blueprint" or quality.get("apply_to_template_source") is not False:
        fail("template source: Code Quality must remain inactive blueprint")

    source_blueprints = [
        "config/security/control-plane-policy.json", "config/security/trust-policy.json", "config/security/threat-model.json",
        "config/runtime/budgets.json", "config/release/release-policy.json", "config/data/data-governance.json",
        "config/operations/operations-policy.json", "config/contracts/migration-policy.json",
        "config/integrations/sync-authority.json", "config/design/design-assurance.json",
        "config/testing/conformance-scenarios.json",
        "config/assurance/assurance-state.json", "config/assurance/runtime-executors.json", "config/research/evidence-registry.json",
    ]
    for path in source_blueprints:
        doc = load_json(path)
        if doc.get("status") != "template_blueprint" or doc.get("activation_scope") != "child_project_only":
            fail(f"template source: {path} must remain template_blueprint/child_project_only")

    active = ROOT / ".github" / "workflows"
    active_workflows = sorted(
        [path.name for path in active.glob("*.yml")] +
        [path.name for path in active.glob("*.yaml")]
    ) if active.exists() else []
    allowed_source_workflows = {
        "source-continuous-certification.yml",
        "immutable-vendor-handoff.yml",
        "commercial-production-deploy.yml",
        "commercial-production-migrate.yml",
        "commercial-production-readiness.yml",
        "commercial-sandbox-live-e2e.yml",
    }
    if not set(active_workflows).issubset(allowed_source_workflows):
        fail("template source: active source workflows must remain in the guarded source-only allowlist")
    for workflow_name in active_workflows:
        workflow_path = active / workflow_name
        source_text = workflow_path.read_text(encoding="utf-8")
        if "github.repository == 'Vertex-Systems-Network/ai-native-project-operating-system'" not in source_text:
            fail(f"template source: {workflow_name} must be repository-guarded")
        if "contents: write" in source_text or "persist-credentials: true" in source_text:
            fail(f"template source: {workflow_name} must remain read-only")
    if (ROOT / ".github" / "dependabot.yml").exists():
        fail("template source: child Dependabot config must not be active")


def validate_control_plane() -> None:
    ownership = load_json("config/github/path-ownership.json")
    rules = load_json("config/github/ruleset-policy.json")
    security = load_json("config/security/control-plane-policy.json")
    trust = load_json("config/security/trust-policy.json")
    patterns = {str(row.get("pattern")) for row in ownership.get("rules", []) if isinstance(row, dict)}
    protected = {str(value) for value in security.get("protected_paths", [])}

    for expected in PROTECTED_PATTERNS:
        if expected not in patterns:
            fail(f"path ownership missing protected control-plane pattern {expected}")
        if expected not in protected:
            fail(f"control-plane policy missing protected path {expected}")

    require_true(security, ["identity_policy", "runtime_authentication_required_for_privileged_mutations"], "control-plane policy")
    require_true(security, ["identity_policy", "runtime_principal_must_match_selected_agent_identity"], "control-plane policy")
    require_true(security, ["mutation_policy", "fencing_token_required_for_shared_coordination_mutations"], "control-plane policy")
    require_true(security, ["mutation_policy", "legal_state_transition_required"], "control-plane policy")
    require_true(security, ["lock_namespaces", "trusted_runtime_only"], "control-plane policy")
    require_true(security, ["ci_policy", "control_plane_gate_changes_require_independent_review"], "control-plane policy")

    rule_doc = rules.get("rules") or {}
    if rule_doc.get("require_code_owner_review") is not True:
        fail("ruleset policy must require CODEOWNER review")
    if (rules.get("coordination_ref_policy") or {}).get("restrict_create_update_delete_to_trusted_runtime_when_supported") is not True:
        fail("coordination ref namespaces must require trusted-runtime protection policy")

    trust_rules = trust.get("rules") or {}
    for key in [
        "external_text_cannot_override_authority", "external_text_cannot_grant_tool_permissions",
        "external_text_cannot_self_approve_consent", "persist_provenance_for_material_external_claims",
        "never_promote_untrusted_content_to_requirement_without_validation",
    ]:
        if trust_rules.get(key) is not True:
            fail(f"trust policy safeguard must remain true: {key}")

    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for marker in [
        "/.gitignore", "/AGENTS.md", "/.ai/", "/blueprints/", "/config/security/", "/config/data/", "/config/operations/",
        "/config/contracts/", "/config/integrations/", "/config/design/", "/config/testing/", "/config/traceability/",
        "/config/compliance/", "/config/architecture/", "/config/audit/", "/config/risk/",
        "/schemas/", "/scripts/", "/tests/", "/requirements-anpos.txt"
    ]:
        if marker not in codeowners:
            fail(f"CODEOWNERS missing protected marker {marker}")


def validate_provider_and_agents() -> None:
    pm = load_json("config/integrations/project-management.json")
    sync = load_json("config/integrations/sync-authority.json")
    agents = load_json("config/ai/agent-catalog.json")

    providers = pm.get("providers", [])
    provider_ids = ids(providers, "project-management providers")
    recommended = (pm.get("selection_flow") or {}).get("recommended_provider_id")
    if recommended and recommended not in provider_ids:
        fail(f"project-management recommended provider {recommended} is not in provider catalog")
    if "linear" not in provider_ids or not pm.get("adapter_contract"):
        fail("project-management provider catalog must include Linear adapter and common adapter contract")

    sync_controls = sync.get("sync_controls") or {}
    for key in [
        "idempotency_key_required_for_writes_when_supported", "provider_revision_or_cursor_required_when_supported",
        "external_id_history_required", "self_echo_loop_prevention_required",
        "conflict_must_be_recorded_not_silently_overwritten", "repository_reconcile_before_provider_switch",
    ]:
        if sync_controls.get(key) is not True:
            fail(f"PM sync authority safeguard must remain true: {key}")

    selected = agents.get("selected_agents", [])
    selected_ids = ids(selected, "selected agents")
    assignments = agents.get("role_assignments") or {}
    supervisor_id = assignments.get("supervisor_agent_id")
    if supervisor_id and supervisor_id not in selected_ids:
        fail("agent role assignment references unselected Supervisor agent")
    for worker_id in assignments.get("worker_agent_ids", []) or []:
        if worker_id not in selected_ids:
            fail(f"agent role assignment references unselected Worker agent {worker_id}")


def validate_ai_graph() -> None:
    options_doc = load_json("config/ai/options-bank.json")
    modules_doc = load_json("config/ai/modules-bank.json")
    execution_doc = load_json("config/ai/execution-plan.json")
    queue_doc = load_json("config/coordination/agent-work-queue.json")
    alerts_doc = load_json("config/coordination/agent-alerts.json")
    consents_doc = load_json("config/consent/consent-requests.json")
    trace_doc = load_json("config/traceability/requirements-traceability.json")

    option_ids = ids(options_doc.get("options", []), "options")
    module_ids = ids(modules_doc.get("modules", []), "modules")
    phase_ids = ids(execution_doc.get("phases", []), "phases")
    work_unit_ids = ids(execution_doc.get("work_units", []), "work_units")
    ids(queue_doc.get("slots", []), "coordination slots")
    ids(alerts_doc.get("alerts", []), "agent alerts")
    ids(consents_doc.get("requests", []), "consent requests")

    for module in modules_doc.get("modules", []):
        if isinstance(module, dict):
            check_refs(module.get("option_ids", []), option_ids, f"module {module.get('id')} option_ids")
            check_refs(module.get("dependencies", []), module_ids, f"module {module.get('id')} dependencies")
    for phase in execution_doc.get("phases", []):
        if isinstance(phase, dict):
            check_refs(phase.get("module_ids", []), module_ids, f"phase {phase.get('id')} module_ids")
            check_refs(phase.get("dependencies", []), phase_ids, f"phase {phase.get('id')} dependencies")
    for unit in execution_doc.get("work_units", []):
        if isinstance(unit, dict):
            if unit.get("phase_id") and unit.get("phase_id") not in phase_ids:
                fail(f"work unit {unit.get('id')}: unknown phase_id {unit.get('phase_id')}")
            if unit.get("module_id") and unit.get("module_id") not in module_ids:
                fail(f"work unit {unit.get('id')}: unknown module_id {unit.get('module_id')}")
            check_refs(unit.get("dependencies", []), work_unit_ids, f"work unit {unit.get('id')} dependencies")
    for link in trace_doc.get("links", []):
        if isinstance(link, dict):
            rid = str(link.get("requirement_id", "<unknown>"))
            check_refs(link.get("option_ids", []), option_ids, f"trace {rid} option_ids")
            check_refs(link.get("module_ids", []), module_ids, f"trace {rid} module_ids")
            check_refs(link.get("work_unit_ids", []), work_unit_ids, f"trace {rid} work_unit_ids")


def validate_coordination() -> None:
    queue = load_json("config/coordination/agent-work-queue.json")
    supervisor = load_json("config/coordination/supervisor-state.json")
    machine = load_json("config/protocol/state-machine.json")

    if int(queue.get("schema_version", 0)) < 4:
        fail("agent-work-queue schema_version must be >=4")
    if int(supervisor.get("schema_version", 0)) < 4:
        fail("supervisor-state schema_version must be >=4")

    q_status = set(queue.get("status_values", []))
    worker_transitions = machine.get("worker_slot_transitions", {})
    if set(worker_transitions) != q_status:
        fail("state-machine worker states must match queue status_values")
    for state, targets in worker_transitions.items():
        if any(target not in q_status for target in targets):
            fail(f"worker state {state} has transition to unknown status")

    queue_lease_states = set(queue.get("lease_status_values", []))
    if queue_lease_states != LEASE_STATES:
        fail("queue lease_status_values must match the hardened lease state set")
    for graph_name in ["worker_lease_transitions", "supervisor_lease_transitions"]:
        graph = machine.get(graph_name, {})
        if set(graph) != LEASE_STATES:
            fail(f"{graph_name} must define every hardened lease state")
        for state, targets in graph.items():
            if any(target not in LEASE_STATES for target in targets):
                fail(f"{graph_name} state {state} targets unknown lease state")

    slot_template = queue.get("slot_schema") or {}
    handoff_keys = {
        "required_roles", "required_capabilities", "allowed_paths", "denied_paths", "allowed_tools",
        "network_policy", "network_allowlist", "pm_scope", "secret_scope", "deployment_scope",
        "acceptance_criteria", "required_checks", "risk_classification", "delegation_depth",
    }
    missing_handoff = handoff_keys - set(slot_template)
    if missing_handoff:
        fail(f"queue slot handoff template missing fields: {sorted(missing_handoff)}")

    sup = supervisor.get("supervisor") or {}
    if sup.get("status") == "active":
        for key in ["agent_id", "identity_ref", "heartbeat_at", "lease_id", "lease_expires_at", "fencing_token", "election_ref"]:
            if sup.get(key) in (None, ""):
                fail(f"active Supervisor missing {key}")
        if sup.get("lease_status") != "active":
            fail("active Supervisor must have active lease_status")

    for slot in queue.get("slots", []):
        if not isinstance(slot, dict):
            continue
        for key in handoff_keys:
            if key not in slot:
                fail(f"slot {slot.get('id')}: missing typed handoff field {key}")
        if slot.get("status") in ACTIVE_SLOT_STATES:
            for key in [
                "claim_ref", "claimant", "claimant_identity_ref", "claim_id", "claim_branch",
                "coordination_epoch", "fencing_token", "lease_expires_at", "base_sha"
            ]:
                if slot.get(key) in (None, ""):
                    fail(f"slot {slot.get('id')}: active claim missing {key}")
            if slot.get("lease_status") != "active":
                fail(f"slot {slot.get('id')}: active claim must have active lease_status")


def validate_consent_and_design() -> None:
    consent = load_json("config/consent/consent-requests.json")
    design = load_json("config/design/design-intake.json")
    assurance = load_json("config/design/design-assurance.json")

    security_rules = consent.get("security_rules") or {}
    for key in [
        "decision_must_match_exact_request_hash", "nonce_is_single_use", "expired_request_cannot_be_approved",
        "changed_request_requires_new_hash_and_consent", "authorized_identity_evidence_required", "replayed_decision_rejected",
    ]:
        if security_rules.get(key) is not True:
            fail(f"consent security rule must remain true: {key}")

    if design.get("approval_status") == "approved":
        if not design.get("approved_by") or not design.get("approved_at"):
            fail("approved design requires approval identity/time")
        if not design.get("version_or_revision") and not design.get("snapshot_ref"):
            fail("approved design requires immutable revision or snapshot evidence")

    verification = assurance.get("verification") or {}
    if verification.get("accessibility_target") != "WCAG_2_2_AA_for_web_unless_overridden":
        fail("design assurance must retain WCAG 2.2 AA default for web")
    for key in ["visual_regression_required_when_material", "design_change_after_approval_requires_impact_analysis"]:
        if verification.get(key) is not True:
            fail(f"design assurance safeguard must remain true: {key}")


def validate_assurance_policies() -> None:
    budgets = load_json("config/runtime/budgets.json")
    release = load_json("config/release/release-policy.json")
    data = load_json("config/data/data-governance.json")
    ops = load_json("config/operations/operations-policy.json")
    migration = load_json("config/contracts/migration-policy.json")
    quality = load_json("config/quality/quality-policy.json")

    limits = budgets.get("limits") or {}
    for key in ["max_parallel_agents", "max_delegation_depth", "max_same_error_retries", "max_tool_retry_attempts"]:
        value = limits.get(key)
        if not isinstance(value, int) or value < 0:
            fail(f"runtime budget {key} must be a non-negative integer")
    for key in ["circuit_breaker_after_repeated_identical_failure", "stop_on_budget_exhaustion", "never_recursively_delegate_without_bounded_depth"]:
        if (budgets.get("policy") or {}).get(key) is not True:
            fail(f"runtime budget safeguard must remain true: {key}")

    rc = release.get("release_candidate") or {}
    for key in [
        "immutable_commit_required", "required_quality_and_security_checks", "migration_preflight_required",
        "release_notes_required", "deployment_plan_required", "rollback_or_rollforward_plan_required",
        "post_deploy_verification_required", "artifact_digest_required_when_artifacts_exist",
    ]:
        if rc.get(key) is not True:
            fail(f"release safeguard must remain true: {key}")
    for key in ["prefer_oidc_short_lived_identity", "untrusted_prs_must_not_access_production_credentials", "environment_secret_separation_required"]:
        if (release.get("deployment_security") or {}).get(key) is not True:
            fail(f"deployment security safeguard must remain true: {key}")

    data_rules = data.get("rules") or {}
    for key in [
        "secrets_never_in_pm_or_ai_memory", "sensitive_logs_must_be_redacted",
        "production_data_copy_to_lower_environment_requires_approval",
        "retention_and_deletion_must_be_defined_before_production_for_sensitive_data",
    ]:
        if data_rules.get(key) is not True:
            fail(f"data governance safeguard must remain true: {key}")

    if (ops.get("recovery") or {}).get("restore_test_required_before_production_for_critical_state") is not True:
        fail("operations policy must require restore testing before production for critical state")
    if (ops.get("incident_policy") or {}).get("post_incident_review_required_for_major_incidents") is not True:
        fail("operations policy must require major-incident review")

    breaking = migration.get("breaking_change_policy") or {}
    for key in [
        "impact_analysis_required", "consumer_compatibility_required", "prefer_expand_migrate_verify_contract",
        "destructive_step_requires_explicit_approval_when_material", "irreversible_step_must_be_labeled",
    ]:
        if breaking.get(key) is not True:
            fail(f"migration safety safeguard must remain true: {key}")

    if quality.get("universal_required_checks") != ["repository-integrity"]:
        fail("quality baseline must keep only repository-integrity universally required before capability detection")
    required_capability_checks = {"dependency-review", "codeql-actions", "ossf-scorecard"}
    if not required_capability_checks.issubset(set(quality.get("capability_dependent_checks", []))):
        fail("quality policy must classify GitHub security checks as capability-dependent")
    require_true(quality, ["quality_gate_rules", "never_require_a_check_until_it_has_run_successfully_in_that_child"], "quality policy")
    require_true(quality, ["quality_gate_rules", "control_plane_validator_changes_require_protected_base_validation_and_independent_review"], "quality policy")


def validate_product_assurance() -> None:
    state = load_json("config/assurance/assurance-state.json")
    rows = state.get("requirements", [])
    ids_seen = {row.get("requirement_id") for row in rows if isinstance(row, dict)}
    expected = {f"REQ-{n}" for n in range(83, 97)}
    if ids_seen != expected:
        fail(f"assurance state must contain exactly requirements 83-96; got {sorted(ids_seen)}")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("state") == "passed":
            if not row.get("evidence_refs") or not row.get("last_verified_ref") or not row.get("last_verified_at"):
                fail(f"{row.get('requirement_id')}: passed assurance requires evidence and verified ref/time")
        if row.get("applicability") == "not_applicable":
            if row.get("state") != "not_applicable" or not str(row.get("reason") or "").strip():
                fail(f"{row.get('requirement_id')}: not_applicable requires matching state and non-empty reason")

    ai = load_json("config/ai/ai-evaluation-policy.json")
    require_true(ai, ["dataset_policy", "versioned_evaluation_set_required"], "AI evaluation policy")
    require_true(ai, ["change_policy", "material_model_change_requires_targeted_reevaluation"], "AI evaluation policy")
    require_true(ai, ["change_policy", "material_prompt_or_system_instruction_change_requires_targeted_reevaluation"], "AI evaluation policy")
    require_true(ai, ["release_gate", "critical_failure_classes_cannot_be_hidden_by_average_score"], "AI evaluation policy")

    analytics = load_json("config/product/product-analytics.json")
    for key in ["deployment_is_not_product_success", "synthetic_traffic_is_not_user_outcome_evidence", "vanity_metrics_must_not_replace_outcome_metrics"]:
        require_true(analytics, ["interpretation_rules", key], "product analytics policy")

    experiment = load_json("config/product/experimentation-policy.json")
    for key in ["no_security_or_privacy_weakening_for_experiment", "no_material_undisclosed_user_risk", "legal_or_consent_requirements_cannot_be_bypassed"]:
        require_true(experiment, ["safety", key], "experimentation policy")

    delivery = load_json("config/release/progressive-delivery.json")
    require_true(delivery, ["feature_flag_policy", "owner_required"], "progressive delivery policy")
    require_true(delivery, ["feature_flag_policy", "cleanup_or_review_date_required"], "progressive delivery policy")
    require_true(delivery, ["feature_flag_policy", "client_side_flag_is_not_authorization_boundary"], "progressive delivery policy")

    review = load_json("config/quality/engineering-review-policy.json")
    require_true(review, ["completion_rules", "critical_correctness_security_or_data_integrity_defect_blocks_completion"], "engineering review policy")
    require_true(review, ["completion_rules", "material_debt_must_be_fixed_deferred_with_rationale_or_tracked"], "engineering review policy")

    executors = load_json("config/assurance/runtime-executors.json")
    executor_requirements = {row.get("requirement_id") for row in executors.get("executors", []) if isinstance(row, dict)}
    expected_executor_requirements = {"REQ-83", "REQ-84", "REQ-85", "REQ-86", "REQ-87", "REQ-88"}
    if executor_requirements != expected_executor_requirements:
        fail("assurance runtime executor contract must cover exactly executable product-assurance requirements 83-88")

    research = load_json("config/research/evidence-registry.json")
    if research.get("entries") not in ([], None) and not isinstance(research.get("entries"), list):
        fail("research evidence entries must be a list")


def validate_governance_assurance() -> None:
    responsible = load_json("config/ai/responsible-ai-policy.json")
    require_true(responsible, ["risk_detection", "detect_high_impact_ai_use"], "responsible AI policy")
    require_true(responsible, ["oversight", "human_review_thresholds_required_when_high_impact"], "responsible AI policy")
    require_true(responsible, ["oversight", "emergency_suspend_or_disable_authority_required"], "responsible AI policy")
    require_true(responsible, ["evaluation", "fairness_or_bias_dimensions_must_be_assessed_for_applicability"], "responsible AI policy")
    require_true(responsible, ["transparency", "known_limitations_must_not_be_presented_as_guarantees"], "responsible AI policy")

    compliance = load_json("config/compliance/compliance-profile.json")
    require_true(compliance, ["controls", "data_purpose_and_category_mapping_required"], "compliance profile")
    require_true(compliance, ["controls", "legal_or_compliance_review_required_for_qualified_regulatory_conclusions"], "compliance profile")

    assets = load_json("config/ai/asset-registry.json")
    require_true(assets, ["rules", "secrets_forbidden"], "AI asset registry")
    require_true(assets, ["rules", "material_configuration_change_invalidates_stale_assurance_when_policy_requires"], "AI asset registry")

    deprecation = load_json("config/contracts/deprecation-policy.json")
    require_true(deprecation, ["rules", "consumer_impact_analysis_required"], "deprecation policy")
    require_true(deprecation, ["rules", "approved_support_window_required_before_removal_when_material"], "deprecation policy")

    runbooks = load_json("config/operations/runbooks-and-drills.json")
    require_true(runbooks, ["rules", "critical_state_restore_or_recovery_runbooks_required"], "runbooks policy")
    require_true(runbooks, ["rules", "unsafe_failure_injection_forbidden"], "runbooks policy")

    audit = load_json("config/audit/audit-journal.json")
    if (audit.get("integrity") or {}).get("mode") != "sha256_hash_chain":
        fail("audit journal must retain sha256_hash_chain integrity mode")
    require_true(audit, ["rules", "secrets_credentials_and_sensitive_full_prompts_forbidden"], "audit journal")
    require_true(audit, ["rules", "integrity_break_requires_investigation_before_trusting_later_entries"], "audit journal")

    risks = load_json("config/risk/risk-register.json")
    require_true(risks, ["rules", "accepted_risk_requires_review_or_expiry"], "risk register")
    require_true(risks, ["rules", "expired_acceptance_reopens_review"], "risk register")
    require_true(risks, ["rules", "critical_release_blockers_cannot_be_hidden_by_generic_acceptance"], "risk register")

    decisions = load_json("config/architecture/decision-records.json")
    instance = load_json("config/protocol/instance.json")
    if instance.get("instance_status") == "template_source":
        for label, values in [
            ("architecture decisions", decisions.get("decisions")),
            ("AI asset registry", assets.get("assets")),
            ("runbooks", runbooks.get("runbooks")),
            ("resilience drills", runbooks.get("drills")),
            ("audit journal", audit.get("entries")),
            ("risk register", risks.get("risks")),
            ("compliance jurisdictions", compliance.get("jurisdictions")),
            ("compliance frameworks", compliance.get("applicable_frameworks")),
        ]:
            if values:
                fail(f"template source: {label} must remain empty")


def validate_blueprint_closure() -> None:
    version = load_json("config/protocol/version.json").get("version")
    completion = load_json("config/protocol/blueprint-completion.json")
    if completion.get("protocol_version") != version:
        fail("blueprint completion manifest protocol_version must match active protocol version")
    rows = completion.get("requirements", [])
    expected_ids = {f"REQ-{n:02d}" for n in range(1, 97)}
    actual_ids = {row.get("requirement_id") for row in rows if isinstance(row, dict)}
    if actual_ids != expected_ids:
        fail("blueprint completion manifest must cover every requirement REQ-01 through REQ-96 exactly once")
    if len(rows) != 96:
        fail("blueprint completion manifest must contain exactly 96 requirement rows")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        for field in ["authoritative_docs", "machine_controls", "verification_refs"]:
            refs = row.get(field, [])
            if not isinstance(refs, list) or not refs:
                fail(f"{row.get('requirement_id')}: {field} must be a non-empty list")
                continue
            for relative in refs:
                if not isinstance(relative, str) or not (ROOT / relative).exists():
                    fail(f"{row.get('requirement_id')}: {field} references missing path {relative}")
        if row.get("coverage_status") != "covered_by_blueprint":
            fail(f"{row.get('requirement_id')}: blueprint coverage status must remain covered_by_blueprint")
        if row.get("runtime_evidence_required_in_child") is not True:
            fail(f"{row.get('requirement_id')}: child runtime evidence boundary must remain true")

    matrix = load_json("config/testing/reference-e2e-matrix.json")
    if matrix.get("protocol_version") != version:
        fail("reference E2E matrix protocol_version must match active protocol version")
    expected_scenarios = {"E2E-FRESH-CHILD", "E2E-EXISTING-ADOPTION", "E2E-PRE14-UPGRADE"}
    scenarios = matrix.get("scenarios", [])
    scenario_ids = {row.get("id") for row in scenarios if isinstance(row, dict)}
    if scenario_ids != expected_scenarios or len(scenarios) != 3:
        fail("reference E2E matrix must define exactly fresh-child, existing-adoption and pre-1.4-upgrade scenarios")
    for row in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("certification_status") != "reference_only":
            fail(f"{row.get('id')}: reference E2E scenario must not claim execution certification")
        for field in ["required_operations", "expected_invariants", "required_evidence", "failure_gates"]:
            if not isinstance(row.get(field), list) or not row.get(field):
                fail(f"{row.get('id')}: {field} must remain non-empty")

    extension = load_json("config/protocol/extension-contract.json")
    if extension.get("protocol_version") != version:
        fail("extension contract protocol_version must match active protocol version")
    if extension.get("current_core_requirement_ceiling") != 96:
        fail("extension contract core requirement ceiling must remain 96 for ANPOS 1.4.0")
    core_rule = extension.get("core_requirement_rule") or {}
    if core_rule.get("next_requirement_id") != "REQ-97":
        fail("extension contract next normative core requirement must be REQ-97")
    if core_rule.get("requirement_ids_are_append_only") is not True or core_rule.get("requirement_ids_must_not_be_reused") is not True:
        fail("extension contract must keep requirement IDs append-only and non-reusable")
    namespace = extension.get("extension_namespace_rule") or {}
    if namespace.get("extensions_must_not_claim_core_requirement_numbers") is not True:
        fail("extensions must not claim core ANPOS requirement numbers")
    if not isinstance(namespace.get("registered_extensions"), list):
        fail("extension registry must remain a list")


def validate_conformance() -> None:
    doc = load_json("config/testing/conformance-scenarios.json")
    scenarios = doc.get("scenarios", [])
    scenario_ids = ids(scenarios, "conformance scenarios")
    names: set[str] = set()
    for index, row in enumerate(scenarios if isinstance(scenarios, list) else []):
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            fail(f"conformance scenario[{index}] missing name")
            continue
        if name in names:
            fail(f"duplicate conformance scenario name {name}")
        names.add(name)
        if not row.get("expected") or not row.get("level"):
            fail(f"conformance scenario {name} missing expected/level")
    if not scenario_ids:
        fail("conformance scenario catalog must not be empty")
    missing = REQUIRED_CONFORMANCE - names
    if missing:
        fail(f"conformance catalog missing required scenarios: {sorted(missing)}")
    if "unit/static checks alone are not sufficient" not in str(doc.get("certification_rule", "")):
        fail("conformance certification rule must distinguish runtime certification from unit/static checks")


def validate_workflow_tree(directory: Path, label: str) -> None:
    action_pattern = re.compile(r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)", re.MULTILINE)
    full_sha = re.compile(r"^[0-9a-fA-F]{40}$")
    for path in sorted(directory.glob("*.y*ml")) if directory.exists() else []:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "permissions:" not in text:
            fail(f"{label} {relative}: explicit permissions block is required")
        if re.search(r"permissions:\s*write-all", text):
            fail(f"{label} {relative}: permissions: write-all is forbidden")
        if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
            fail(f"{label} {relative}: pull_request_target requires explicit security exception")
        if "persist-credentials: true" in text:
            fail(f"{label} {relative}: checkout persist-credentials must not be true")
        if "comment-summary-in-pr: always" in text and "pull-requests: write" not in text:
            fail(f"{label} {relative}: PR commenting requested without pull-requests: write")
        if "source /tmp/protocol-env" in text:
            fail(f"{label} {relative}: repository-derived shell environment must not be sourced")
        for match in action_pattern.finditer(text):
            action, ref = match.groups()
            if not action.startswith("./") and not full_sha.fullmatch(ref):
                fail(f"{label} {relative}: {action}@{ref} is not pinned to a full 40-character commit SHA")


def validate_workflows() -> None:
    validate_workflow_tree(ROOT / "blueprints" / "github" / "workflows", "blueprint")
    validate_workflow_tree(ROOT / ".github" / "workflows", "active")

    quality_path = ROOT / "blueprints" / "github" / "workflows" / "repository-quality.yml"
    text = quality_path.read_text(encoding="utf-8") if quality_path.exists() else ""
    for marker in [
        "requirements-anpos.txt", "python -m compileall -q scripts tests",
        "python -m unittest discover -s tests -p 'test_*.py'", "python scripts/validate_ai_native_repo.py",
        "git show \"${BASE_SHA}:scripts/validate_ai_native_repo.py\"", "python scripts/.trusted-base-validator.py",
    ]:
        if marker not in text:
            fail(f"repository-quality blueprint missing trusted/conformance gate marker: {marker}")


def main() -> int:
    validate_required_files()
    validate_json_schemas()
    validate_manifest()
    validate_protocol_versioning()
    validate_template_boundary()
    validate_control_plane()
    validate_provider_and_agents()
    validate_ai_graph()
    validate_coordination()
    validate_consent_and_design()
    validate_assurance_policies()
    validate_product_assurance()
    validate_governance_assurance()
    validate_blueprint_closure()
    validate_conformance()
    validate_workflows()

    if ERRORS:
        print("ANPOS repository validation failed:", file=sys.stderr)
        for error in ERRORS:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("ANPOS repository integrity and hardening checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
