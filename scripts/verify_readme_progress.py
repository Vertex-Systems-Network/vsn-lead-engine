#!/usr/bin/env python3
"""Fail closed when AI-native README status or autonomous resume rules drift."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- ANPOS-CONTINUITY:BEGIN -->"
END = "<!-- ANPOS-CONTINUITY:END -->"
COUNTS = ("complete", "in_progress", "blocked", "deferred", "not_started")
PROGRESS_PATHS = (
    "apps/saas/",
    "apps/web/",
    "src/",
    "config/ai/project-state.json",
    "config/ai/execution-plan.json",
    "config/ai/modules-bank.json",
    ".ai/state/CURRENT-STATE.yaml",
    ".ai/state/LAST-CHECKPOINT.md",
)


def validate_repository(root: Path, changed_paths: list[str] | None = None) -> list[str]:
    """Validate the machine-state mirror without inventing runtime verification."""
    errors: list[str] = []
    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
        plan = json.loads((root / "config/ai/project-state.json").read_text(encoding="utf-8"))
        supervisor = json.loads(
            (root / "config/coordination/supervisor-state.json").read_text(encoding="utf-8")
        )
        recovery = (root / ".ai/state/RECOVERY-PROTOCOL.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return [f"Cannot read canonical continuity inputs: {exc}"]

    if readme.count(BEGIN) != 1 or readme.count(END) != 1:
        return ["README.md must contain exactly one bounded ANPOS continuity dashboard"]
    block = readme.split(BEGIN, 1)[1].split(END, 1)[0]
    match = re.search(
        r"Work units: \*\*(\d+) complete / (\d+) in progress / "
        r"(\d+) blocked / (\d+) deferred / (\d+) not started "
        r"\((\d+) total\)\*\*",
        block,
    )
    if not match:
        errors.append("README continuity dashboard must expose five counts and total")
    else:
        expected = tuple(plan.get("progress", {}).get(key) for key in COUNTS)
        actual = tuple(int(n) for n in match.groups()[:5])
        expected_total = plan.get("progress", {}).get("total_work_units")
        if actual != expected or int(match.group(6)) != expected_total:
            errors.append(f"README work-unit counts {actual} differ from project-state {expected}")
        if sum(actual) != int(match.group(6)):
            errors.append("README work-unit categories must add up to their total")

    snapshot = re.search(r"Verified plan snapshot: \*\*(\d{4}-\d{2}-\d{2})\*\*", block)
    if not snapshot or snapshot.group(1) != plan.get("last_reconciled_at"):
        errors.append("README verified plan snapshot must match project-state reconciliation date")

    mode = re.search(r"Runtime mode: `([a-z0-9_]+)`", block)
    if not mode or mode.group(1) != supervisor.get("runtime_mode"):
        errors.append("README runtime mode must match the actual Supervisor mirror")

    next_unit = re.search(r"Next work unit: `([A-Z0-9_-]+)`", block)
    if not next_unit or next_unit.group(1) != plan.get("next_valid_work_unit"):
        errors.append("README next work unit must match project-state")

    if "Default to one logical milestone per" in recovery:
        errors.append("Recovery protocol still contains the conflicting one-milestone stop default")
    if "milestone completion is a checkpoint, not a stop condition" not in recovery.lower():
        errors.append("Recovery protocol must explicitly continue after a checkpoint")

    if changed_paths is not None:
        meaningful = any(
            path.startswith(prefix) for path in changed_paths for prefix in PROGRESS_PATHS
        )
        if meaningful and "README.md" not in changed_paths:
            errors.append(
                "Development or machine-progress changes need a README.md update in the same PR"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Git commit to compare with HEAD for PR progress enforcement")
    args = parser.parse_args()
    changed: list[str] | None = None
    if args.base:
        try:
            changed = subprocess.check_output(
                ["git", "diff", "--name-only", args.base, "HEAD", "--"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.STDOUT,
            ).splitlines()
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Unable to compare progress changes to PR base: {exc}", file=sys.stderr)
            return 2
    errors = validate_repository(ROOT, changed)
    if errors:
        for error in errors:
            print(f"ANPOS continuity: {error}", file=sys.stderr)
        return 1
    print("ANPOS continuity: README counts/runtime/next work and recovery guard verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
