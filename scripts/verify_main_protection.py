from __future__ import annotations

import argparse
import json

from github_ruleset_common import (
    admin_token,
    find_ruleset,
    get_ruleset,
    load_policy,
    policy_diff,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify live GitHub main-branch protection against repository policy."
    )
    parser.add_argument(
        "--allow-missing-token",
        action="store_true",
        help="Return a structured unavailable result instead of failing when no admin token exists.",
    )
    args = parser.parse_args()

    policy = load_policy()
    try:
        token = admin_token()
    except RuntimeError as exc:
        if not args.allow_missing_token:
            raise
        print(json.dumps({
            "status": "unavailable",
            "protected": False,
            "reason": str(exc),
            "ruleset_name": policy["name"],
        }, indent=2))
        return 0

    existing = find_ruleset(policy["name"], token=token)
    if not existing:
        print(json.dumps({
            "status": "missing",
            "protected": False,
            "ruleset_name": policy["name"],
        }, indent=2))
        return 2

    actual = get_ruleset(int(existing["id"]), token=token)
    drift = policy_diff(policy, actual)
    result = {
        "status": "ok" if not drift else "drift",
        "protected": not drift and actual.get("enforcement") == "active",
        "ruleset_id": int(existing["id"]),
        "ruleset_name": policy["name"],
        "enforcement": actual.get("enforcement"),
        "drift": drift,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["protected"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
