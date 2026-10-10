"""Regression tests for the product-progress stop-loss gate."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_product_progress import evaluate


class ProductProgressTests(unittest.TestCase):
    def test_new_or_modified_batch_module_is_frozen(self) -> None:
        for status in ("A", "M"):
            errors = evaluate([(status, "apps/saas/core/batch_settlement.py")], ["src/x.py"])
            self.assertTrue(any("frozen" in e for e in errors))

    def test_batch_test_module_is_frozen(self) -> None:
        errors = evaluate([("A", "apps/saas/core/test_batch_new.py")], ["src/x.py"])
        self.assertTrue(any("frozen" in e for e in errors))

    def test_deleting_batch_module_is_allowed(self) -> None:
        self.assertEqual(evaluate([("D", "apps/saas/core/batch_settlement.py")], ["README.md"]), [])

    def test_customer_path_code_passes(self) -> None:
        self.assertEqual(evaluate([("M", "apps/saas/core/dispatch.py"), ("M", "README.md")], ["README.md"]), [])

    def test_chained_state_only_prs_fail(self) -> None:
        errors = evaluate([("M", "README.md"), ("M", ".ai/state/CURRENT-STATE.yaml")], ["README.md", "config/ai/project-state.json"])
        self.assertTrue(any("previous merge" in e for e in errors))

    def test_state_only_pr_after_code_merge_passes(self) -> None:
        self.assertEqual(evaluate([("M", "README.md")], ["src/vsn_lead_engine/engine.py", "README.md"]), [])

    def test_markdown_under_code_paths_is_not_code(self) -> None:
        errors = evaluate([("M", "apps/saas/README.md")], ["docs/ai/X.md"])
        self.assertTrue(any("previous merge" in e for e in errors))

    def test_unknown_base_history_does_not_block(self) -> None:
        self.assertEqual(evaluate([("M", "README.md")], None), [])


if __name__ == "__main__":
    unittest.main()
