from __future__ import annotations

import argparse
import json

from github_ruleset_common import (
    admin_token,
    api_request,
    find_ruleset,
    get_ruleset,
    load_policy,
    policy_diff,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update the VSN main-branch protection ruleset."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for any GitHub-side mutation.",
    )
    args = parser.parse_args()

    policy = load_policy()
    token = admin_token()
    existing = find_ruleset(policy["name"], token=token)

    if not args.confirm:
        preview = {
            "status": "plan",
            "action": "update" if existing else "create",
            "ruleset_name": policy["name"],
            "existing_ruleset_id": existing.get("id") if existing else None,
            "policy": policy,
        }
        print(json.dumps(preview, indent=2))
        return 0

    if existing:
        ruleset_id = int(existing["id"])
        api_request(
            "PUT",
            f"/rulesets/{ruleset_id}",
            token=token,
            payload=policy,
        )
        action = "updated"
    else:
        created = api_request(
            "POST",
            "/rulesets",
            token=token,
            payload=policy,
        )
        ruleset_id = int(created["id"])
        action = "created"

    actual = get_ruleset(ruleset_id, token=token)
    drift = policy_diff(policy, actual)
    result = {
        "status": "ok" if not drift else "drift",
        "action": action,
        "ruleset_id": ruleset_id,
        "ruleset_name": policy["name"],
        "enforcement": actual.get("enforcement"),
        "drift": drift,
    }
    print(json.dumps(result, indent=2))
    return 0 if not drift else 2


if __name__ == "__main__":
    raise SystemExit(main())
