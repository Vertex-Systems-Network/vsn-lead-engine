"""Bounded configuration visibility, never provider/rights activation."""

from django.db import transaction

from .job_history import locked_workspace
from .models import SourcePolicy

CATALOG_LIMIT = 100


def capability_values(value):
    # Treat corrupt/legacy metadata as unknown, never iterate a string/dict as a list.
    if not isinstance(value, list) or len(value) > 100:
        return None
    if not all(isinstance(item, str) and len(item) <= 120 for item in value):
        return None
    return value


@transaction.atomic
def source_preview(user, workspace_id):
    workspace = locked_workspace(user, workspace_id)
    policies = list(SourcePolicy.objects.order_by("code")[: CATALOG_LIMIT + 1])
    entries = [
        {
            "code": policy.code,
            "version": policy.version,
            "configured_enabled": policy.enabled,
            "configured_free_collection": policy.free_collection,
            "countries": capability_values(policy.countries),
            "categories": capability_values(policy.categories),
            "statuses": capability_values(policy.statuses),
            "fields": capability_values(policy.fields),
        }
        for policy in policies[:CATALOG_LIMIT]
    ]
    return workspace, entries, len(policies) > CATALOG_LIMIT
