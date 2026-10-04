#!/usr/bin/env python3
"""Generate child Dependabot ecosystems from repository manifests.

This helper intentionally covers common package managers and GitHub Actions.
The Architecture/SQA role must review unusual monorepo/custom ecosystem needs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".github" / "dependabot.yml"

DETECTORS = [
    ("npm", {"package.json"}),
    ("composer", {"composer.json"}),
    ("pip", {"requirements.txt", "pyproject.toml", "Pipfile"}),
    ("gomod", {"go.mod"}),
    ("cargo", {"Cargo.toml"}),
    ("bundler", {"Gemfile"}),
    ("maven", {"pom.xml"}),
    ("gradle", {"build.gradle", "build.gradle.kts"}),
    ("docker", {"Dockerfile"}),
]
IGNORE_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "dist", "build"}


def candidate_dirs():
    found: dict[tuple[str, str], None] = {("github-actions", "/"): None}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORE_DIRS for part in path.parts):
            continue
        for ecosystem, names in DETECTORS:
            if path.name in names:
                rel = path.parent.relative_to(ROOT).as_posix()
                directory = "/" if rel == "." else f"/{rel}"
                found[(ecosystem, directory)] = None
    return sorted(found)


def render(entries):
    lines = ["version: 2", "updates:"]
    for ecosystem, directory in entries:
        lines.extend([
            f"  - package-ecosystem: {ecosystem}",
            f"    directory: \"{directory}\"",
            "    schedule:",
            "      interval: weekly",
            "      day: monday",
            "      time: \"03:00\"",
            "      timezone: \"Etc/UTC\"",
            "    open-pull-requests-limit: 10",
        ])
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    entries = candidate_dirs()
    text = render(entries)
    print(text, end="")
    if not args.apply:
        print("# DRY RUN - no file written")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"Generated {OUT.relative_to(ROOT)} for {len(entries)} ecosystem/directory entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
