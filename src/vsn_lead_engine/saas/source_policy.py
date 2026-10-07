from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from .contracts import Entitlement, ExportSpec, SearchSpec


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """Rights and capability boundary for one discovery source."""

    code: str
    countries: FrozenSet[str]
    categories: FrozenSet[str] = frozenset()
    allowed_required_fields: FrozenSet[str] = frozenset()
    storage_allowed: bool = True
    export_allowed: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("source code is required")
        if not self.countries:
            raise ValueError("source must declare supported countries")


class SearchAuthorizationError(ValueError):
    """Raised when a workspace search exceeds entitlement or source policy."""


def authorize_search(
    search: SearchSpec,
    entitlement: Entitlement,
    policies: dict[str, SourcePolicy],
) -> None:
    if search.workspace_id != entitlement.workspace_id:
        raise SearchAuthorizationError("search workspace does not match entitlement")
    if not entitlement.active:
        raise SearchAuthorizationError("workspace entitlement is inactive")
    if not search.source_codes:
        raise SearchAuthorizationError("at least one source must be selected")
    if not set(search.source_codes).issubset(entitlement.source_codes):
        raise SearchAuthorizationError("selected source is not included in the plan")

    for code in search.source_codes:
        policy = policies.get(code)
        if policy is None or not policy.enabled:
            raise SearchAuthorizationError(f"source is unavailable: {code}")
        if policy.code != code:
            raise SearchAuthorizationError(f"source policy identity mismatch: {code}")
        if not set(search.countries).issubset(policy.countries):
            raise SearchAuthorizationError(f"source does not support requested countries: {code}")
        if policy.categories and not set(search.categories).issubset(policy.categories):
            raise SearchAuthorizationError(f"source does not support requested categories: {code}")
        if not set(search.required_fields).issubset(policy.allowed_required_fields):
            raise SearchAuthorizationError(f"source cannot provide requested fields: {code}")
        if not policy.storage_allowed:
            raise SearchAuthorizationError(f"source does not permit storage: {code}")

    if entitlement.lead_limit is not None and search.result_limit > entitlement.lead_limit:
        raise SearchAuthorizationError("requested result limit exceeds lead entitlement")


def authorize_export(
    export: ExportSpec,
    entitlement: Entitlement,
    policies: dict[str, SourcePolicy],
) -> None:
    """Authorize an export against tenant entitlement and source field rights."""
    if export.workspace_id != entitlement.workspace_id:
        raise SearchAuthorizationError("export workspace does not match entitlement")
    if not entitlement.active:
        raise SearchAuthorizationError("workspace entitlement is inactive")
    if not entitlement.export_enabled:
        raise SearchAuthorizationError("export is disabled for this plan")
    if not set(export.source_codes).issubset(entitlement.source_codes):
        raise SearchAuthorizationError("selected source is not included in the plan")

    for code in export.source_codes:
        policy = policies.get(code)
        if policy is None or not policy.enabled:
            raise SearchAuthorizationError(f"source is unavailable: {code}")
        if policy.code != code:
            raise SearchAuthorizationError(f"source policy identity mismatch: {code}")
        if not policy.export_allowed:
            raise SearchAuthorizationError(f"source does not permit export: {code}")
        if not set(export.fields).issubset(policy.allowed_required_fields):
            raise SearchAuthorizationError(f"source does not permit exported fields: {code}")
