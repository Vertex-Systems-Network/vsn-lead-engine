"""Regression tests for explicit autonomous continuation and README truthfulness."""
from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path

# pytest and unittest discovery may start with tests/ as sys.path[0].
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_readme_progress import validate_repository


class ContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for directory in ("config/ai", "config/coordination", ".ai/state"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "config/ai/project-state.json").write_text(
            json.dumps(
                {
                    "progress": {
                        "complete": 9,
                        "in_progress": 5,
                        "blocked": 1,
                        "deferred": 2,
                        "not_started": 4,
                        "total_work_units": 21,
                    },
                    "last_reconciled_at": "2026-10-08",
                    "next_valid_work_unit": "WU-SAAS-FOUNDATION",
                }
            ),
            encoding="utf-8",
        )
        (self.root / "config/coordination/supervisor-state.json").write_text(
            json.dumps({"runtime_mode": "degraded_no_verified_supervisor"}),
            encoding="utf-8",
        )
        (self.root / ".ai/state/RECOVERY-PROTOCOL.md").write_text(
            "A milestone completion is a checkpoint, not a stop condition.",
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "<!-- ANPOS-CONTINUITY:BEGIN -->\n"
            "Verified plan snapshot: **2026-10-08**\n"
            "Runtime mode: `degraded_no_verified_supervisor`\n"
            "Work units: **9 complete / 5 in progress / 1 blocked / "
            "2 deferred / 4 not started (21 total)**\n"
            "Next work unit: `WU-SAAS-FOUNDATION`\n"
            "<!-- ANPOS-CONTINUITY:END -->\n",
            encoding="utf-8",
        )

    def test_verified_snapshot_passes(self) -> None:
        self.assertEqual(validate_repository(self.root, ["README.md", "apps/saas/model.py"]), [])

    def test_readme_count_drift_fails(self) -> None:
        path = self.root / "README.md"
        path.write_text(path.read_text().replace("9 complete", "8 complete"), encoding="utf-8")
        self.assertTrue(any("counts" in e for e in validate_repository(self.root)))

    def test_legacy_stop_rule_fails(self) -> None:
        path = self.root / ".ai/state/RECOVERY-PROTOCOL.md"
        path.write_text(
            path.read_text() + "\nDefault to one logical milestone per continue turn.",
            encoding="utf-8",
        )
        self.assertTrue(any("one-milestone" in e for e in validate_repository(self.root)))

    def test_code_change_requires_same_pr_readme(self) -> None:
        errors = validate_repository(self.root, ["apps/saas/models.py"])
        self.assertTrue(any("same PR" in e for e in errors))

    def test_unrelated_change_does_not_require_readme(self) -> None:
        self.assertEqual(validate_repository(self.root, ["docs/example.md"]), [])

    def test_unverified_runtime_cannot_be_painted_as_active(self) -> None:
        path = self.root / "README.md"
        path.write_text(
            path.read_text().replace("degraded_no_verified_supervisor", "active_supervisor"),
            encoding="utf-8",
        )
        self.assertTrue(any("runtime mode" in e for e in validate_repository(self.root)))


if __name__ == "__main__":
    unittest.main()
