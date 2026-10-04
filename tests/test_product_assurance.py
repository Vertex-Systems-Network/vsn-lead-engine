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


class ProductAssuranceTests(unittest.TestCase):
    def test_specialized_schemas_validate_current_blueprints(self) -> None:
        mapping = {
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

    def test_assurance_state_covers_exact_requirements_83_96(self) -> None:
        state = load("config/assurance/assurance-state.json")
        rows = state["requirements"]
        self.assertEqual(
            {row["requirement_id"] for row in rows},
            {f"REQ-{n}" for n in range(83, 97)},
        )
        for row in rows:
            self.assertNotEqual(row["state"], "passed", "Template source must not claim assurance pass evidence")

    def test_runtime_executor_contract_covers_all_assurance_requirements(self) -> None:
        contract = load("config/assurance/runtime-executors.json")
        rows = contract["executors"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {row["requirement_id"] for row in rows},
            {"REQ-83", "REQ-84", "REQ-85", "REQ-86", "REQ-87", "REQ-88"},
        )
        for row in rows:
            self.assertTrue(row["required_capabilities"])
            self.assertTrue(row["required_inputs"])
            self.assertTrue(row["required_outputs"])

    def test_conformance_catalog_contains_assurance_scenarios(self) -> None:
        doc = load("config/testing/conformance-scenarios.json")
        names = {row["name"] for row in doc["scenarios"]}
        expected = {
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
        self.assertTrue(expected.issubset(names))

    def test_140_is_active_and_next_release_is_unplanned(self) -> None:
        current = load("config/protocol/version.json")
        planned = load("config/protocol/next-release.json")
        self.assertEqual(current["version"], "1.4.0")
        self.assertEqual(planned["current_version"], current["version"])
        self.assertIsNone(planned["planned_version"])
        self.assertEqual(planned["status"], "unplanned")

    def test_child_bootstrap_dry_run_includes_assurance_state(self) -> None:
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
            "config/assurance/assurance-state.json",
            "config/assurance/runtime-executors.json",
            "config/research/evidence-registry.json",
            "config/ai/ai-evaluation-policy.json",
            "config/product/product-validation.json",
            "config/product/product-analytics.json",
            "config/product/experimentation-policy.json",
            "config/release/progressive-delivery.json",
            "config/quality/engineering-review-policy.json",
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

    def test_source_boundaries_protect_new_control_plane(self) -> None:
        policy = load("config/security/control-plane-policy.json")
        ownership = load("config/github/path-ownership.json")
        protected = set(policy["protected_paths"])
        patterns = {row["pattern"] for row in ownership["rules"]}
        for marker in ["/config/assurance/**", "/config/research/**", "/config/compliance/**", "/config/architecture/**", "/config/audit/**", "/config/risk/**"]:
            self.assertIn(marker, protected)
            self.assertIn(marker, patterns)
        vendor = load("config/licensing/vendor-source-boundary.json")
        self.assertIn("config/protocol/next-release.json", vendor["vendor_only_paths"])


if __name__ == "__main__":
    unittest.main()
