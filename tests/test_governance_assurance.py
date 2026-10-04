from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class GovernanceAssuranceTests(unittest.TestCase):
    def test_governance_schemas_validate_blueprints(self) -> None:
        mapping = {
            "config/ai/responsible-ai-policy.json": "schemas/responsible-ai-policy.schema.json",
            "config/compliance/compliance-profile.json": "schemas/compliance-profile.schema.json",
            "config/architecture/decision-records.json": "schemas/decision-records.schema.json",
            "config/ai/asset-registry.json": "schemas/ai-asset-registry.schema.json",
            "config/contracts/deprecation-policy.json": "schemas/deprecation-policy.schema.json",
            "config/operations/runbooks-and-drills.json": "schemas/runbooks-and-drills.schema.json",
            "config/audit/audit-journal.json": "schemas/audit-journal.schema.json",
            "config/risk/risk-register.json": "schemas/risk-register.schema.json",
        }
        for instance_path, schema_path in mapping.items():
            with self.subTest(instance=instance_path):
                schema = load(schema_path)
                Draft202012Validator.check_schema(schema)
                errors = sorted(
                    Draft202012Validator(schema).iter_errors(load(instance_path)),
                    key=lambda e: list(e.absolute_path),
                )
                self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_requirements_89_96_exist_and_do_not_claim_pass(self) -> None:
        state = load("config/assurance/assurance-state.json")
        rows = {row["requirement_id"]: row for row in state["requirements"]}
        expected = {f"REQ-{n}" for n in range(89, 97)}
        self.assertTrue(expected.issubset(rows))
        for rid in expected:
            self.assertNotEqual(rows[rid]["state"], "passed")

    def test_responsible_ai_has_human_override_and_transparency_safeguards(self) -> None:
        policy = load("config/ai/responsible-ai-policy.json")
        self.assertTrue(policy["oversight"]["human_review_thresholds_required_when_high_impact"])
        self.assertTrue(policy["oversight"]["emergency_suspend_or_disable_authority_required"])
        self.assertTrue(policy["oversight"]["appeal_or_correction_path_required_when_materially_affecting_people"])
        self.assertTrue(policy["transparency"]["known_limitations_must_not_be_presented_as_guarantees"])

    def test_compliance_policy_does_not_self_authorize_legal_conclusions(self) -> None:
        profile = load("config/compliance/compliance-profile.json")
        self.assertTrue(profile["controls"]["legal_or_compliance_review_required_for_qualified_regulatory_conclusions"])
        self.assertIn("ANPOS must not invent a legal conclusion.", profile["rules"])

    def test_ai_asset_registry_forbids_secrets_and_invalidates_stale_assurance(self) -> None:
        registry = load("config/ai/asset-registry.json")
        self.assertTrue(registry["rules"]["secrets_forbidden"])
        self.assertTrue(registry["rules"]["material_configuration_change_invalidates_stale_assurance_when_policy_requires"])
        self.assertEqual(registry["assets"], [])

    def test_risk_acceptance_is_time_bounded(self) -> None:
        risks = load("config/risk/risk-register.json")
        self.assertTrue(risks["rules"]["accepted_risk_requires_review_or_expiry"])
        self.assertTrue(risks["rules"]["expired_acceptance_reopens_review"])
        self.assertTrue(risks["rules"]["critical_release_blockers_cannot_be_hidden_by_generic_acceptance"])

    def test_audit_journal_is_tamper_evident_and_secret_safe(self) -> None:
        audit = load("config/audit/audit-journal.json")
        self.assertEqual(audit["integrity"]["mode"], "sha256_hash_chain")
        self.assertTrue(audit["rules"]["secrets_credentials_and_sensitive_full_prompts_forbidden"])
        self.assertTrue(audit["rules"]["integrity_break_requires_investigation_before_trusting_later_entries"])
        self.assertEqual(audit["entries"], [])

    def test_governance_conformance_scenarios_exist(self) -> None:
        scenarios = {row["name"] for row in load("config/testing/conformance-scenarios.json")["scenarios"]}
        expected = {
            "high_impact_ai_without_required_human_oversight",
            "regulated_or_sensitive_processing_without_required_compliance_evidence",
            "accepted_architecture_decision_silently_reversed",
            "ai_asset_configuration_drift_after_certified_evaluation",
            "deprecated_contract_removed_before_approved_support_window",
            "critical_recovery_runbook_or_resilience_drill_failure",
            "audit_journal_integrity_chain_break",
            "expired_risk_acceptance_used_to_bypass_gate",
        }
        self.assertTrue(expected.issubset(scenarios))

    def test_child_bootstrap_includes_governance_state(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/bootstrap_instance.py",
                "--repository",
                "example/example-child",
                "--project-name",
                "Example Child",
                "--github-owner",
                "example-owner",
                "--github-security-capability",
                "unavailable",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for marker in [
            "config/ai/responsible-ai-policy.json",
            "config/compliance/compliance-profile.json",
            "config/architecture/decision-records.json",
            "config/ai/asset-registry.json",
            "config/contracts/deprecation-policy.json",
            "config/operations/runbooks-and-drills.json",
            "config/audit/audit-journal.json",
            "config/risk/risk-register.json",
        ]:
            self.assertIn(marker, proc.stdout)

    def test_governance_paths_are_protected(self) -> None:
        protected = set(load("config/security/control-plane-policy.json")["protected_paths"])
        owned = {row["pattern"] for row in load("config/github/path-ownership.json")["rules"]}
        required = {
            "/AI-NATIVE-GOVERNANCE-ASSURANCE.md",
            "/config/ai/responsible-ai-policy.json",
            "/config/ai/asset-registry.json",
            "/config/compliance/**",
            "/config/architecture/**",
            "/config/audit/**",
            "/config/risk/**",
        }
        self.assertTrue(required.issubset(protected))
        self.assertTrue(required.issubset(owned))


if __name__ == "__main__":
    unittest.main()
