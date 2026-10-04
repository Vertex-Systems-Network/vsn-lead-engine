#!/usr/bin/env python3
"""Install optional child GitHub security/quality blueprints after capability detection.

The caller must determine platform capability through authenticated GitHub/API
inspection. This script never guesses licensing/feature availability.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = ROOT / "blueprints" / "github" / "workflows"
ACTIVE = ROOT / ".github" / "workflows"
QUALITY = ROOT / "config" / "quality" / "quality-policy.json"
MAP = {
    "codeql": "codeql-actions.yml",
    "dependency-review": "dependency-review.yml",
    "scorecard": "scorecard.yml",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--enable", nargs="*", choices=sorted(MAP), default=[])
    p.add_argument("--unavailable", nargs="*", choices=sorted(MAP), default=[])
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    overlap = set(args.enable) & set(args.unavailable)
    if overlap:
        raise SystemExit(f"Capabilities cannot be both enabled and unavailable: {sorted(overlap)}")

    plan = {name: ("enable" if name in args.enable else "unavailable" if name in args.unavailable else "pending") for name in MAP}
    print(json.dumps(plan, indent=2))
    if not args.apply:
        print("DRY RUN - no workflows installed or state changed.")
        return 0

    ACTIVE.mkdir(parents=True, exist_ok=True)
    for name in args.enable:
        source = BLUEPRINTS / MAP[name]
        if not source.exists():
            raise SystemExit(f"Missing blueprint {source}")
        shutil.copyfile(source, ACTIVE / MAP[name])

    quality = json.loads(QUALITY.read_text(encoding="utf-8"))
    setup = quality.setdefault("setup_state", {})
    setup["capability_resolution"] = "resolved" if all(v != "pending" for v in plan.values()) else "partial"
    setup["github_security_features"] = plan
    installed = set(setup.get("installed_blueprints") or [])
    installed.update(MAP[name] for name in args.enable)
    setup["installed_blueprints"] = sorted(installed)
    quality["setup_state"] = setup
    QUALITY.write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    print("Capability-aware quality workflow state updated. Run/observe workflows before requiring their check names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
