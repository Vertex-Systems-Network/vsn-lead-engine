from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import anpos_guard
import consent_guard
from coordination_mutation import validate_queue_transitions


class ControlPlaneGuardTests(unittest.TestCase):
    def agent(self, capabilities=None, allowed_paths=None):
        return {
            "id": "worker-1",
            "provider": "test",
            "roles": ["worker"],
            "capabilities": capabilities or ["repository_write"],
            "permissions": {
                "allowed_paths": allowed_paths or ["src/**"],
                "denied_paths": ["config/security/**"],
                "allowed_tools": ["git", "pytest"],
                "network_policy": "allowlist_only",
                "network_allowlist": ["api.example.com"],
                "pm_scope": ["assigned_task_write"],
                "secret_scope": "no_secrets",
                "deployment_scope": "no_deploy",
            },
        }

    def verified_agent(self):
        agent = self.agent()
        agent.update({
            "identity_verified": True,
            "runtime_identity": {
                "principal_id": "principal-1",
                "provider": "test-runtime",
                "evidence_ref": "runtime://principal-1",
                "verified_at": "2026-09-03T00:00:00+00:00",
                "expires_at": "2099-09-03T00:00:00+00:00",
            },
        })
        return agent

    def base_slot(self):
        return {
            "id": "SLOT-1",
            "work_unit_id": "WU-1",
            "eligibility": ["ANY"],
            "required_roles": ["worker"],
            "required_capabilities": ["repository_write"],
            "allowed_paths": ["src/auth/**"],
            "denied_paths": [],
            "allowed_tools": ["git"],
            "network_policy": "allowlist_only",
            "network_allowlist": ["api.example.com"],
            "pm_scope": "assigned_task_write",
            "secret_scope": "none",
            "deployment_scope": "none",
            "acceptance_criteria": ["works"],
            "required_checks": ["tests"],
            "risk_classification": "normal",
            "base_sha": "a" * 40,
        }

    def test_supervisor_only_slot_rejects_worker(self):
        slot = self.base_slot()
        slot["eligibility"] = ["SUPERVISOR_ONLY"]
        with patch.object(anpos_guard, "require_verified_agent", return_value=self.agent()):
            with self.assertRaises(PermissionError):
                anpos_guard.authorize_slot_claim(slot, "worker-1", "worker")

    def test_missing_capability_rejected(self):
        slot = self.base_slot()
        slot["required_capabilities"] = ["security_review"]
        with patch.object(anpos_guard, "require_verified_agent", return_value=self.agent()):
            with self.assertRaises(PermissionError):
                anpos_guard.authorize_slot_claim(slot, "worker-1", "worker")

    def test_path_permission_violation_rejected(self):
        slot = self.base_slot()
        slot["allowed_paths"] = ["config/security/**"]
        with self.assertRaises(PermissionError):
            anpos_guard.authorize_slot_paths(slot, self.agent())

    def test_control_plane_path_requires_control_plane_capability(self):
        slot = self.base_slot()
        slot["allowed_paths"] = ["config/security/**"]
        agent = self.agent(allowed_paths=["**"])
        agent["permissions"]["denied_paths"] = []
        with self.assertRaises(PermissionError):
            anpos_guard.authorize_slot_paths(slot, agent)

    def test_incomplete_handoff_rejected(self):
        slot = self.base_slot()
        slot["required_checks"] = []
        with self.assertRaises(ValueError):
            anpos_guard.validate_handoff(slot)

    def test_network_allowlist_escalation_rejected(self):
        slot = self.base_slot()
        slot["network_allowlist"] = ["evil.example.net"]
        with self.assertRaises(PermissionError):
            anpos_guard.authorize_runtime_scope(slot, self.agent())

    def test_pm_scope_escalation_rejected(self):
        slot = self.base_slot()
        slot["pm_scope"] = "project_admin"
        with self.assertRaises(PermissionError):
            anpos_guard.authorize_runtime_scope(slot, self.agent())

    def test_tool_scope_escalation_rejected(self):
        slot = self.base_slot()
        slot["allowed_tools"] = ["git", "cloud-admin"]
        with self.assertRaises(PermissionError):
            anpos_guard.authorize_runtime_scope(slot, self.agent())

    def test_runtime_principal_mismatch_rejected(self):
        agent = self.verified_agent()
        with patch.object(anpos_guard, "selected_agent", return_value=agent):
            with patch.dict(os.environ, {"ANPOS_RUNTIME_PRINCIPAL": "other-principal"}, clear=False):
                with self.assertRaises(PermissionError):
                    anpos_guard.require_verified_agent("worker-1", "worker")

    def test_matching_runtime_principal_accepted(self):
        agent = self.verified_agent()
        with patch.object(anpos_guard, "selected_agent", return_value=agent):
            with patch.dict(os.environ, {"ANPOS_RUNTIME_PRINCIPAL": "principal-1"}, clear=False):
                self.assertEqual(anpos_guard.require_verified_agent("worker-1", "worker")["id"], "worker-1")

    def test_expired_runtime_identity_rejected(self):
        agent = self.verified_agent()
        agent["runtime_identity"]["expires_at"] = "2020-01-01T00:00:00+00:00"
        with patch.object(anpos_guard, "selected_agent", return_value=agent):
            with patch.dict(os.environ, {"ANPOS_RUNTIME_PRINCIPAL": "principal-1"}, clear=False):
                with self.assertRaises(PermissionError):
                    anpos_guard.require_verified_agent("worker-1", "worker")


class CoordinationMutationTests(unittest.TestCase):
    def test_illegal_transition_rejected(self):
        old = {"slots": [{"id": "S1", "status": "free"}]}
        new = {"slots": [{"id": "S1", "status": "completed"}]}
        with self.assertRaises(PermissionError):
            validate_queue_transitions(old, new)

    def test_active_claim_identity_cannot_silently_change(self):
        old = {"slots": [{
            "id": "S1", "status": "in_progress", "claimant": "a", "claim_id": "1",
            "coordination_epoch": 1, "fencing_token": "f",
        }]}
        new = copy.deepcopy(old)
        new["slots"][0]["claimant"] = "b"
        with self.assertRaises(PermissionError):
            validate_queue_transitions(old, new)


class ConsentIntegrityTests(unittest.TestCase):
    def record(self):
        return {
            "id": "CONSENT-000001",
            "type": "material_change",
            "title": "Upgrade",
            "summary": "Upgrade A",
            "proposed_changes": ["A"],
            "affected_modules": ["M1"],
            "risk": "medium",
            "owner_identity": "owner",
            "requested_at": "2026-09-03T00:00:00+00:00",
            "expires_at": "2026-09-04T00:00:00+00:00",
            "nonce": "nonce-1234567890",
        }

    def test_changed_request_changes_hash(self):
        first = self.record()
        second = copy.deepcopy(first)
        second["summary"] = "Upgrade B"
        self.assertNotEqual(consent_guard.request_hash(first), consent_guard.request_hash(second))

    def test_changed_nonce_changes_hash(self):
        first = self.record()
        second = copy.deepcopy(first)
        second["nonce"] = "nonce-different"
        self.assertNotEqual(consent_guard.request_hash(first), consent_guard.request_hash(second))

    def test_decided_consent_requires_nonempty_identity_and_hash_evidence(self):
        schema = json.loads((ROOT / "schemas/consent-requests.schema.json").read_text())
        doc = {
            "schema_version": 2,
            "next_sequence": 2,
            "status_values": ["pending", "approved", "partially_approved", "rejected", "expired", "implemented", "verified", "closed"],
            "security_rules": {
                "decision_must_match_exact_request_hash": True,
                "nonce_is_single_use": True,
                "expired_request_cannot_be_approved": True,
                "authorized_identity_evidence_required": True,
                "replayed_decision_rejected": True,
            },
            "requests": [{
                "id": "CONSENT-000001",
                "type": "material_change",
                "requested_at": "2026-09-03T00:00:00+00:00",
                "request_hash": "a" * 64,
                "nonce": "1234567890abcdef",
                "expires_at": "2026-09-04T00:00:00+00:00",
                "status": "approved",
                "decision_by": None,
                "decision_identity_evidence_ref": None,
                "decision_at": None,
                "decision_evidence": None,
                "decision_request_hash": None,
                "nonce_consumed_at": None,
            }],
        }
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(doc)))


class DesignSchemaTests(unittest.TestCase):
    def test_approved_design_requires_nonempty_revision_or_snapshot(self):
        schema = json.loads((ROOT / "schemas/design-intake.schema.json").read_text())
        doc = json.loads((ROOT / "config/design/design-intake.json").read_text())
        doc.update({
            "approval_status": "approved",
            "approved_by": "owner",
            "approved_at": "2026-09-03T00:00:00+00:00",
            "version_or_revision": None,
            "snapshot_ref": None,
        })
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(doc)))


class TemplatePolicyTests(unittest.TestCase):
    def test_conformance_manifest_has_required_scenarios(self):
        doc = json.loads((ROOT / "config/testing/conformance-scenarios.json").read_text())
        names = {row["name"] for row in doc["scenarios"]}
        required = {
            "two_workers_same_slot", "unauthorized_worker_restricted_slot", "stale_fencing_token",
            "orphan_claim_ref", "supervisor_crash_failover", "duplicate_event_replay",
            "malicious_external_instruction", "consent_expiry_replay_or_hash_mismatch",
            "control_plane_validator_tampering", "agent_budget_retry_loop",
            "selected_agent_unavailable_or_identity_expired", "tool_network_pm_or_secret_scope_escalation",
            "pm_sync_conflict_or_echo_loop", "release_missing_required_evidence", "approved_design_revision_drift",
            "destructive_migration_without_valid_consent", "backup_restore_or_recovery_verification_failure",
        }
        self.assertTrue(required.issubset(names))

    def test_source_has_no_live_agent_selection(self):
        catalog = json.loads((ROOT / "config/ai/agent-catalog.json").read_text())
        self.assertEqual(catalog.get("selected_agents"), [])
        self.assertEqual(catalog.get("available_agents"), [])

    def test_source_template_has_only_allowlisted_guarded_source_workflows(self):
        instance = json.loads((ROOT / "config/protocol/instance.json").read_text())
        if instance.get("instance_status") != "template_source":
            self.skipTest("source-template workflow invariant does not apply after child bootstrap")
        workflow_dir = ROOT / ".github" / "workflows"
        active = sorted(
            [p.name for p in workflow_dir.glob("*.yml")] +
            [p.name for p in workflow_dir.glob("*.yaml")]
        ) if workflow_dir.exists() else []
        allowed = {
            "source-continuous-certification.yml",
            "immutable-vendor-handoff.yml",
            "commercial-production-deploy.yml",
            "commercial-production-migrate.yml",
            "commercial-production-readiness.yml",
        "commercial-sandbox-live-e2e.yml",
        }
        self.assertTrue(set(active).issubset(allowed))
        for name in active:
            source = (workflow_dir / name).read_text()
            self.assertIn(
                "github.repository == 'Vertex-Systems-Network/ai-native-project-operating-system'",
                source,
            )
            self.assertNotIn("contents: write", source)
            self.assertNotIn("persist-credentials: true", source)

    def test_worker_handoff_template_has_network_and_pm_scope(self):
        queue = json.loads((ROOT / "config/coordination/agent-work-queue.json").read_text())
        template = queue["slot_schema"]
        self.assertIn("network_allowlist", template)
        self.assertIn("pm_scope", template)


if __name__ == "__main__":
    unittest.main()
