"""Consistent tenant-scoped usage visibility; never a customer balance mutation."""

from django.db import transaction
from django.db.models import Sum

from .models import Entitlement, UsageCounter, UsageReservation, Workspace
from .services import membership_for
from .usage import COUNTERS


@transaction.atomic
def usage_snapshot(user, workspace_id):
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership_for(user, workspace_id, lock=True)
    entitlement = Entitlement.objects.filter(workspace_id=workspace_id).first()
    counter = UsageCounter.objects.filter(workspace_id=workspace_id).first()
    pending = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    return {
        "workspace_id": str(workspace_id),
        "entitlement_active": bool(entitlement and entitlement.active),
        "period": {
            "id": str(counter.period_id),
            "starts_at": counter.period.starts_at,
            "ends_at": counter.period.ends_at,
        }
        if counter and counter.period_id
        else None,
        "reset_at": None,
        "accounting": "period_development"
        if counter and counter.period_id
        else "cumulative_development",
        "counters": {
            name: {
                "settled": getattr(counter, name, 0),
                "reserved": pending[name] or 0,
                "limit": getattr(entitlement, limit, 0),
            }
            for name, limit in COUNTERS.items()
        },
    }
