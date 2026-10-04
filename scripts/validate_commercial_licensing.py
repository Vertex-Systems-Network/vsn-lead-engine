#!/usr/bin/env python3
"""Validate ANPOS commercial distribution/licensing blueprint invariants.

This validator checks repository-side contracts only. It does not claim that a
Marketplace listing, GitHub App, payment account, entitlement database, webhook
endpoint, signing key, or customer license service is deployed or operational.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

try:
    from jsonschema import Draft202012Validator
except Exception:
    Draft202012Validator = None

REQUIRED_FILES = [
    "COMMERCIAL-LICENSING.md",
    "config/licensing/commercial-policy.json",
    "config/licensing/product-catalog.json",
    "config/licensing/marketplace-adapter.json",
    "config/licensing/entitlement-reference.json",
    "schemas/license-entitlement.schema.json",
    "blueprints/commercial/marketplace-webhook-contract.json",
    "blueprints/commercial/entitlement-envelope.example.json",
    "blueprints/commercial/service-api-contract.json",
    "scripts/validate_commercial_licensing.py",
    "tests/test_commercial_licensing.py",
]

REQUIRED_COMMERCIAL_CONFORMANCE = {
    "marketplace_webhook_forgery_or_replay",
    "entitlement_expiry_non_destructive",
    "marketplace_plan_change_entitlement_reconciliation",
}


def fail(message: str) -> None:
    ERRORS.append(message)


def load(path: str) -> dict[str, Any]:
    try:
        value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"{path}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        fail(f"{path}: top-level JSON must be an object")
        return {}
    return value


def require_true(doc: dict[str, Any], path: list[str], label: str) -> None:
    value: Any = doc
    for key in path:
        if not isinstance(value, dict):
            fail(f"{label}: missing {'.'.join(path)}")
            return
        value = value.get(key)
    if value is not True:
        fail(f"{label}: {'.'.join(path)} must be true")


def validate_files() -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing commercial licensing file: {relative}")


def validate_source_boundary() -> None:
    instance = load("config/protocol/instance.json")
    if instance.get("instance_status") != "template_source":
        return

    policy = load("config/licensing/commercial-policy.json")
    adapter = load("config/licensing/marketplace-adapter.json")
    reference = load("config/licensing/entitlement-reference.json")
    catalog = load("config/licensing/product-catalog.json")

    if policy.get("status") != "template_blueprint":
        fail("template source: commercial policy must remain template_blueprint")
    if policy.get("activation_scope") != "commercial_distribution_only":
        fail("template source: commercial policy activation must remain commercial_distribution_only")
    if policy.get("enabled") is not False:
        fail("template source: commercial runtime must remain disabled")
    if adapter.get("status") != "template_blueprint" or adapter.get("configured") is not False:
        fail("template source: Marketplace adapter must remain unconfigured blueprint")
    if reference.get("state") != "unbound" or reference.get("authority") is not False:
        fail("template source: entitlement reference must remain unbound/non-authoritative")
    if (reference.get("verification") or {}).get("status") != "not_verified":
        fail("template source: entitlement reference must not claim verification")
    for key in ["license_id", "github_account_id", "plan_id", "issued_at", "not_before", "expires_at", "signed_entitlement"]:
        if reference.get(key) not in (None, ""):
            fail(f"template source: entitlement runtime field {key} must be empty")
    if catalog.get("pricing_is_external_to_repository") is not True:
        fail("template source: pricing must remain external to repository")
    for plan in catalog.get("plans", []):
        if not isinstance(plan, dict):
            fail("product catalog: each plan must be an object")
            continue
        if plan.get("sale_status") != "draft":
            fail(f"template source: plan {plan.get('id')} must remain draft until operator configures sale")
        for key in ["marketplace_plan_id", "monthly_price_usd", "annual_price_usd"]:
            if plan.get(key) is not None:
                fail(f"template source: draft plan {plan.get('id')} field {key} must remain null")


def validate_authority_and_safety() -> None:
    policy = load("config/licensing/commercial-policy.json")
    adapter = load("config/licensing/marketplace-adapter.json")
    webhook = load("blueprints/commercial/marketplace-webhook-contract.json")

    authority = policy.get("authority") or {}
    if authority.get("repository_entitlement_cache_is_authority") is not False:
        fail("commercial authority: repository entitlement cache must never be authority")
    require_true(policy, ["authority", "server_side_entitlement_ledger_required"], "commercial policy")
    require_true(policy, ["authority", "billing_provider_reconciliation_required_on_ambiguity"], "commercial policy")
    require_true(policy, ["entitlement_security", "asymmetric_signed_entitlements_required_for_portable_claims"], "commercial policy")
    require_true(policy, ["entitlement_security", "private_signing_key_forbidden_in_repository"], "commercial policy")
    require_true(policy, ["entitlement_security", "webhook_secret_forbidden_in_repository"], "commercial policy")
    require_true(policy, ["entitlement_security", "repository_cache_may_not_self_grant_entitlements"], "commercial policy")

    expiry = policy.get("non_destructive_expiry") or {}
    for key in [
        "existing_generated_project_must_continue",
        "remote_repository_deletion_for_license_expiry_forbidden",
        "intentional_build_breakage_for_license_expiry_forbidden",
        "code_or_data_encryption_kill_switch_forbidden",
    ]:
        if expiry.get(key) is not True:
            fail(f"non-destructive expiry safeguard must remain true: {key}")

    wh = adapter.get("webhook") or {}
    if wh.get("event") != "marketplace_purchase":
        fail("Marketplace adapter must consume marketplace_purchase events")
    if set(wh.get("supported_actions", [])) != {"purchased", "changed", "cancelled"}:
        fail("Marketplace adapter must handle purchased/changed/cancelled actions")
    if wh.get("signature_header") != "X-Hub-Signature-256":
        fail("Marketplace adapter must verify X-Hub-Signature-256")
    if wh.get("delivery_id_header") != "X-GitHub-Delivery":
        fail("Marketplace adapter must deduplicate X-GitHub-Delivery")
    for key in [
        "raw_body_must_be_preserved_until_signature_verification",
        "constant_time_signature_compare_required",
        "delivery_id_deduplication_required",
        "out_of_order_or_ambiguous_event_requires_api_reconciliation",
    ]:
        if wh.get(key) is not True:
            fail(f"Marketplace webhook safeguard must remain true: {key}")

    constraints = adapter.get("listing_constraints") or {}
    if constraints.get("paid_listing_requires_verified_publisher") is not True:
        fail("Marketplace paid listing must retain verified-publisher launch gate")
    if constraints.get("paid_plan_requires_monthly_and_annual_usd_prices") is not True:
        fail("Marketplace paid plan must retain monthly+annual pricing launch gate")
    if constraints.get("constraints_must_be_rechecked_against_current_github_docs_before_launch") is not True:
        fail("Marketplace constraints must be rechecked before commercial launch")

    secrets = adapter.get("secrets") or {}
    for key in ["webhook_secret_in_repository", "github_app_private_key_in_repository", "entitlement_signing_private_key_in_repository"]:
        if secrets.get(key) is not False:
            fail(f"Marketplace secret boundary must remain false: {key}")
    if secrets.get("secrets_manager_required") is not True:
        fail("Marketplace runtime must require an approved secrets manager")

    cancellation = webhook.get("cancellation") or {}
    for key in ["generated_customer_repository_is_not_deleted", "generated_project_code_is_not_modified"]:
        if cancellation.get(key) is not True:
            fail(f"commercial cancellation safeguard must remain true: {key}")


def validate_entitlement_schema() -> None:
    if Draft202012Validator is None:
        fail("jsonschema dependency missing; install requirements-anpos.txt before commercial validation")
        return
    schema = load("schemas/license-entitlement.schema.json")
    reference = load("config/licensing/entitlement-reference.json")
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for error in validator.iter_errors(reference):
            location = "/".join(str(value) for value in error.absolute_path) or "<root>"
            fail(f"entitlement reference [{location}]: {error.message}")
    except Exception as exc:
        fail(f"license entitlement schema validation failed: {exc}")


def validate_catalog() -> None:
    catalog = load("config/licensing/product-catalog.json")
    plans = catalog.get("plans")
    if not isinstance(plans, list) or not plans:
        fail("product catalog must contain at least one draft plan")
        return
    ids: set[str] = set()
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        plan_id = plan.get("id")
        if not isinstance(plan_id, str) or not plan_id:
            fail("product plan missing id")
            continue
        if plan_id in ids:
            fail(f"duplicate commercial plan id: {plan_id}")
        ids.add(plan_id)
        entitlements = plan.get("entitlements")
        if not isinstance(entitlements, list) or not entitlements:
            fail(f"commercial plan {plan_id} must define feature entitlements")


def validate_service_contract() -> None:
    service = load("blueprints/commercial/service-api-contract.json")
    endpoints = service.get("endpoints")
    if not isinstance(endpoints, list):
        fail("commercial service API contract endpoints must be a list")
        return
    seen = {(row.get("method"), row.get("path")) for row in endpoints if isinstance(row, dict)}
    required = {
        ("POST", "/webhooks/github/marketplace"),
        ("GET", "/v1/entitlements/current"),
        ("GET", "/v1/keys"),
        ("POST", "/v1/provision"),
        ("POST", "/v1/reconcile"),
    }
    missing = required - seen
    if missing:
        fail(f"commercial service API contract missing endpoints: {sorted(missing)}")
    rules = service.get("cross_cutting_rules") or {}
    for key in [
        "canonical_subject_is_github_numeric_account_id",
        "authorization_is_server_side",
        "repository_reference_is_not_authorization",
        "rate_limiting_required",
        "structured_audit_logging_required",
        "sensitive_fields_redacted_from_logs",
        "no_remote_kill_switch_for_generated_customer_projects",
    ]:
        if rules.get(key) is not True:
            fail(f"commercial service API safeguard must remain true: {key}")


def validate_conformance() -> None:
    conformance = load("config/testing/conformance-scenarios.json")
    names = {
        row.get("name")
        for row in conformance.get("scenarios", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    missing = REQUIRED_COMMERCIAL_CONFORMANCE - names
    if missing:
        fail(f"missing commercial conformance scenarios: {sorted(missing)}")
    commercial = [
        row for row in conformance.get("scenarios", [])
        if isinstance(row, dict) and row.get("name") in REQUIRED_COMMERCIAL_CONFORMANCE
    ]
    if any(row.get("level") != "commercial_runtime_integration" for row in commercial):
        fail("commercial conformance scenarios must require commercial_runtime_integration")


def validate_protection_and_routing() -> None:
    manifest = load(".ai/manifest.json")
    ownership = load("config/github/path-ownership.json")
    control = load("config/security/control-plane-policy.json")

    role = (manifest.get("roles") or {}).get("commercial_distribution")
    if not isinstance(role, list):
        fail("manifest must define commercial_distribution role")
    else:
        required_role_paths = {
            "COMMERCIAL-LICENSING.md",
            "config/licensing/commercial-policy.json",
            "config/licensing/product-catalog.json",
            "config/licensing/marketplace-adapter.json",
            "config/licensing/entitlement-reference.json",
            "blueprints/commercial/service-api-contract.json",
            "scripts/validate_commercial_licensing.py",
        }
        missing = required_role_paths - set(role)
        if missing:
            fail(f"commercial_distribution role missing paths: {sorted(missing)}")

    patterns = {
        str(row.get("pattern"))
        for row in ownership.get("rules", [])
        if isinstance(row, dict)
    }
    protected = {str(value) for value in control.get("protected_paths", [])}
    for expected in ["/COMMERCIAL-LICENSING.md", "/config/licensing/**"]:
        if expected not in patterns:
            fail(f"path ownership missing commercial protected pattern {expected}")
        if expected not in protected:
            fail(f"control-plane policy missing commercial protected path {expected}")

    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    for expected in ["/COMMERCIAL-LICENSING.md", "/config/licensing/"]:
        if expected not in codeowners:
            fail(f"CODEOWNERS missing commercial marker {expected}")

    commercial_boundary = control.get("commercial_security_boundary") or {}
    for key in [
        "billing_entitlement_state_external_to_repository",
        "webhook_and_signing_secrets_forbidden_in_repository",
        "commercial_policy_changes_require_protected_review",
        "license_expiry_must_not_be_used_as_destructive_project_control",
    ]:
        if commercial_boundary.get(key) is not True:
            fail(f"control-plane commercial safeguard must remain true: {key}")


def validate_quality_integration() -> None:
    workflow = (ROOT / "blueprints" / "github" / "workflows" / "repository-quality.yml").read_text(encoding="utf-8")
    for marker in [
        "python scripts/validate_commercial_licensing.py",
        "tests -p 'test_*.py'",
        "config/licensing COMMERCIAL-LICENSING.md",
    ]:
        if marker not in workflow:
            fail(f"repository quality blueprint missing commercial validation marker: {marker}")


def validate_documentation() -> None:
    text = (ROOT / "COMMERCIAL-LICENSING.md").read_text(encoding="utf-8")
    for marker in [
        "## 75 — Distribution modes",
        "## 76 — Billing and commerce authority",
        "## 77 — Signed entitlement envelope",
        "## 78 — Webhook security, replay protection, and idempotency",
        "## 79 — Non-destructive expiration/cancellation",
        "## 80 — Plans, seats, and entitlements",
        "## 81 — Customer data and privacy",
        "## 82 — Commercial launch, legal, and operational gates",
    ]:
        if marker not in text:
            fail(f"commercial documentation missing requirement marker: {marker}")
    if "ANPOS does **not** invent legally binding license terms" not in text:
        fail("commercial documentation must retain legal-boundary statement")


def main() -> int:
    validate_files()
    if not ERRORS:
        validate_source_boundary()
        validate_authority_and_safety()
        validate_entitlement_schema()
        validate_catalog()
        validate_service_contract()
        validate_conformance()
        validate_protection_and_routing()
        validate_quality_integration()
        validate_documentation()

    if ERRORS:
        print("ANPOS commercial licensing validation failed:", file=sys.stderr)
        for error in ERRORS:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("ANPOS commercial licensing blueprint checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
