"""Read-only internal daily plan preflight; never grants execution permission.

Catalog flags are operator-maintained metadata, not legal/source-rights evidence.
No plan, job, reservation or provider is ever changed or contacted here.
"""

from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from .jobs import CONTROLS, EVIDENCE, nonempty_mapping
from .models import DailySchedule, Entitlement, Membership, SourcePolicy
from .schedules import fingerprint, validate_clock
from .serializers import SearchSerializer
from .services import membership_for


def daily_plan_readiness(actor, workspace_id, plan_id):
    membership = membership_for(actor, workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners and admins can review daily plan policy preflight.")
    plan = DailySchedule.objects.filter(pk=plan_id, workspace_id=workspace_id).first()
    if plan is None:
        raise Http404("Workspace resource not found.")

    checks = []
    def record(name, passed):
        checks.append({"name": name, "status": "pass" if passed else "blocked"})
        return passed

    serializer = SearchSerializer(data=plan.search)
    valid_search = serializer.is_valid() and serializer.validated_data == plan.search
    valid_clock = False
    if valid_search:
        try:
            validate_clock(plan.timezone, plan.local_time)
            valid_clock = (
                plan.revision >= 1
                and fingerprint(plan.search, plan.timezone, plan.local_time) == plan.request_hash
            )
        except (ValueError, TypeError, AttributeError):
            valid_clock = False
    stored_ok = record("stored_plan_snapshot", bool(valid_search and valid_clock))

    active_creator = Membership.objects.filter(
        user_id=plan.created_by_id,
        workspace_id=workspace_id,
        role__in=["owner", "admin", "member"],
    ).exists()
    record("creator_membership", active_creator)

    entitlement = Entitlement.objects.filter(workspace_id=workspace_id).first()
    current_entitlement = entitlement is not None and entitlement.is_current
    record("entitlement_current", current_entitlement)

    source_codes = serializer.validated_data["source_codes"] if stored_ok else []
    selected = record("explicit_source_selection", bool(source_codes))
    catalog_matches = False
    count = 0
    if stored_ok and selected:
        policies = list(SourcePolicy.objects.filter(code__in=source_codes).order_by("code"))
        count = len(policies)
        catalog_matches = len(policies) == len(source_codes)
        for policy in policies:
            allowed = {
                "countries": policy.countries,
                "categories": policy.categories,
                "statuses": policy.statuses,
                "required_fields": policy.fields,
            }
            if (
                not policy.enabled
                or not policy.free_collection
                or policy.version < 1
                or not nonempty_mapping(policy.evidence, EVIDENCE)
                or not nonempty_mapping(policy.controls, CONTROLS)
                or not 1 <= policy.max_provider_calls <= 2147483647
            ):
                catalog_matches = False
            for key, supported in allowed.items():
                if (
                    not isinstance(supported, list)
                    or not all(isinstance(x, str) for x in supported)
                    or not set(serializer.validated_data[key]).issubset(supported)
                ):
                    catalog_matches = False
    record("internal_source_catalog_match", catalog_matches)
    # Even passing catalog metadata cannot prove real capacity, legal rights,
    # price, deployed credentials, provider health, or safe auto-execution.
    return {
        "workspace_id": str(workspace_id),
        "plan_id": str(plan.id),
        "stored_enabled": plan.enabled,
        "advisory_only": True,
        "status": "blocked" if any(row["status"] == "blocked" for row in checks)
        else "internal_catalog_match_only",
        "checked_source_count": count,
        "checks": checks,
        "unverified_execution_gates": [
            "current_usable_quota",
            "source_commercial_rights",
            "provider_credentials_and_health",
            "scheduler_fencing_and_observability",
            "operator_release_and_deployment",
        ],
    }
