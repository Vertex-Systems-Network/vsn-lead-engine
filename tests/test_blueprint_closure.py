from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class BlueprintClosureTests(unittest.TestCase):
    def test_closure_schemas_validate(self) -> None:
        mapping = {
            "config/protocol/blueprint-completion.json": "schemas/blueprint-completion.schema.json",
            "config/testing/reference-e2e-matrix.json": "schemas/reference-e2e-matrix.schema.json",
            "config/protocol/extension-contract.json": "schemas/extension-contract.schema.json",
        }
        for instance_path, schema_path in mapping.items():
            with self.subTest(instance=instance_path):
                schema = load(schema_path)
                Draft202012Validator.check_schema(schema)
                errors = list(Draft202012Validator(schema).iter_errors(load(instance_path)))
                self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_every_core_requirement_1_96_is_covered_once(self) -> None:
        completion = load("config/protocol/blueprint-completion.json")
        rows = completion["requirements"]
        self.assertEqual(len(rows), 96)
        self.assertEqual(
            {row["requirement_id"] for row in rows},
            {f"REQ-{n:02d}" for n in range(1, 97)},
        )
        for row in rows:
            self.assertEqual(row["coverage_status"], "covered_by_blueprint")
            self.assertTrue(row["runtime_evidence_required_in_child"])
            for field in ("authoritative_docs", "machine_controls", "verification_refs"):
                self.assertTrue(row[field])
                for relative in row[field]:
                    self.assertTrue((ROOT / relative).exists(), f"{row['requirement_id']} missing {relative}")

    def test_closure_protocol_identity_matches_active_protocol(self) -> None:
        current = load("config/protocol/version.json")["version"]
        self.assertEqual(load("config/protocol/blueprint-completion.json")["protocol_version"], current)
        self.assertEqual(load("config/testing/reference-e2e-matrix.json")["protocol_version"], current)
        self.assertEqual(load("config/protocol/extension-contract.json")["protocol_version"], current)

    def test_reference_e2e_matrix_has_exact_three_repository_states(self) -> None:
        matrix = load("config/testing/reference-e2e-matrix.json")
        scenarios = {row["id"]: row for row in matrix["scenarios"]}
        self.assertEqual(
            set(scenarios),
            {"E2E-FRESH-CHILD", "E2E-EXISTING-ADOPTION", "E2E-PRE14-UPGRADE"},
        )
        for row in scenarios.values():
            self.assertEqual(row["certification_status"], "reference_only")
            self.assertTrue(row["required_evidence"])
            self.assertTrue(row["failure_gates"])

    def test_future_core_and_extension_growth_is_controlled(self) -> None:
        contract = load("config/protocol/extension-contract.json")
        self.assertEqual(contract["current_core_requirement_ceiling"], 96)
        self.assertEqual(contract["core_requirement_rule"]["next_requirement_id"], "REQ-97")
        self.assertTrue(contract["core_requirement_rule"]["requirement_ids_are_append_only"])
        self.assertTrue(contract["core_requirement_rule"]["requirement_ids_must_not_be_reused"])
        self.assertTrue(contract["extension_namespace_rule"]["extensions_must_not_claim_core_requirement_numbers"])
        self.assertEqual(contract["extension_namespace_rule"]["registered_extensions"], [])

    def test_blueprint_complete_is_not_runtime_complete(self) -> None:
        completion_text = (ROOT / "config/protocol/blueprint-completion.json").read_text(encoding="utf-8")
        matrix_text = (ROOT / "config/testing/reference-e2e-matrix.json").read_text(encoding="utf-8")
        self.assertIn("runtime_evidence_required_in_child", completion_text)
        self.assertIn("reference_only", matrix_text)


if __name__ == "__main__":
    unittest.main()
