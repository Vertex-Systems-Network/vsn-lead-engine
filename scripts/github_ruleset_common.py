from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_VERSION = "2026-03-10"
DEFAULT_REPOSITORY = "Vertex-Systems-Network/vsn-lead-engine"
POLICY_PATH = Path(".github/main-protection-ruleset.json")


def repository_name() -> str:
    value = str(os.getenv("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)).strip()
    if "/" not in value:
        raise RuntimeError(f"Invalid GitHub repository name: {value!r}")
    return value


def admin_token() -> str:
    token = str(
        os.getenv("GITHUB_ADMIN_TOKEN")
        or os.getenv("GH_ADMIN_TOKEN")
        or ""
    ).strip()
    if not token:
        raise RuntimeError(
            "GITHUB_ADMIN_TOKEN or GH_ADMIN_TOKEN is required for GitHub ruleset administration."
        )
    return token


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("target") != "branch":
        raise RuntimeError("Main protection policy must target branches.")
    if payload.get("enforcement") != "active":
        raise RuntimeError("Main protection policy must use active enforcement.")
    return payload


def api_request(
    method: str,
    path: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    repository = repository_name()
    url = f"https://api.github.com/repos/{repository}{path}"
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "VSN-Lead-Engine-Protection-Controller",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API {method.upper()} {path} failed with HTTP {exc.code}: {raw[:1000]}"
        ) from exc


def list_rulesets(*, token: str) -> list[dict[str, Any]]:
    result = api_request("GET", "/rulesets", token=token)
    if not isinstance(result, list):
        raise RuntimeError("GitHub rulesets response must be a list.")
    return result


def get_ruleset(ruleset_id: int, *, token: str) -> dict[str, Any]:
    result = api_request("GET", f"/rulesets/{int(ruleset_id)}", token=token)
    if not isinstance(result, dict):
        raise RuntimeError("GitHub ruleset response must be an object.")
    return result


def find_ruleset(name: str, *, token: str) -> dict[str, Any] | None:
    for item in list_rulesets(token=token):
        if str(item.get("name", "")).strip() == name:
            return item
    return None


def canonical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": policy.get("name"),
        "target": policy.get("target"),
        "enforcement": policy.get("enforcement"),
        "bypass_actors": policy.get("bypass_actors", []),
        "conditions": policy.get("conditions", {}),
        "rules": policy.get("rules", []),
    }


def normalize_ruleset(ruleset: dict[str, Any]) -> dict[str, Any]:
    return canonical_policy(ruleset)


def policy_diff(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_norm = canonical_policy(expected)
    actual_norm = normalize_ruleset(actual)
    return {
        key: {
            "expected": expected_norm[key],
            "actual": actual_norm[key],
        }
        for key in expected_norm
        if expected_norm[key] != actual_norm[key]
    }
