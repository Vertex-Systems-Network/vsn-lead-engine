#!/usr/bin/env python3
"""Fail closed when autonomous work drifts away from shippable product code.

Two stop-loss rules, both derived from git rather than hand-edited state:

1. The quarantined v3 batch-evidence modules are frozen. A PR may delete them
   but may not add to or modify them; new work belongs on the customer path.
2. A PR that changes no code may not directly follow another merge that also
   changed no code, so state/checkpoint/reconcile-only PRs cannot chain.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_PATTERNS = (
    "apps/saas/core/batch_*.py",
    "apps/saas/core/test_batch_*.py",
)
CODE_PREFIXES = (
    "src/",
    "apps/",
    "scripts/",
    "tests/",
    "schemas/",
    ".github/workflows/",
)


def is_frozen(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in FROZEN_PATTERNS)


def is_code(path: str) -> bool:
    return path.startswith(CODE_PREFIXES) and not path.endswith(".md")


def evaluate(changes: list[tuple[str, str]], previous_merge_paths: list[str] | None) -> list[str]:
    """Return errors for (status, path) PR changes and the base tip's changed paths."""
    errors: list[str] = []
    frozen = sorted(path for status, path in changes if status != "D" and is_frozen(path))
    if frozen:
        errors.append(
            "v3 batch-evidence modules are frozen (stop-loss); deletions only. "
            "Move this work to the customer job-fulfilment path: " + ", ".join(frozen)
        )
    pr_has_code = any(is_code(path) for _, path in changes)
    if changes and not pr_has_code and previous_merge_paths is not None:
        if not any(is_code(path) for path in previous_merge_paths):
            errors.append(
                "This PR changes no code and the previous merge to main also changed no code. "
                "Fold state/checkpoint/README reconciliation into the next code PR instead."
            )
    return errors


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def _pr_changes(base: str) -> list[tuple[str, str]]:
    changes = []
    for line in _git("diff", "--name-status", "--no-renames", f"{base}...HEAD").splitlines():
        if line.strip():
            status, path = line.split("\t", 1)
            changes.append((status[0], path))
    return changes


def _base_tip_paths(base: str) -> list[str] | None:
    try:
        output = _git("show", "--first-parent", "--name-only", "--format=", base)
    except subprocess.CalledProcessError:
        return None
    return [line for line in output.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR base commit")
    args = parser.parse_args()
    errors = evaluate(_pr_changes(args.base), _base_tip_paths(args.base))
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("Product-progress stop-loss verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
