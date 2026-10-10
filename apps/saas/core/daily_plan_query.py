"""Read-only, tenant-scoped UUID-cursor daily plan listing.

This function does not activate plans, calculate occurrences or dispatch work.
"""
from uuid import UUID

from rest_framework.exceptions import ValidationError

from .models import DailySchedule
from .services import membership_for

PAGE_SIZE = 25


def daily_plans_page(user, workspace_id, params):
    membership_for(user, workspace_id)
    if set(params) - {"after"} or any(len(params.getlist(key)) != 1 for key in params):
        raise ValidationError("Unsupported or repeated daily plan query parameter.")
    after = None
    if "after" in params:
        try:
            after = UUID(params["after"])
        except (ValueError, AttributeError, TypeError):
            raise ValidationError({"after": "Invalid daily plan cursor."}) from None
    query = DailySchedule.objects.filter(workspace_id=workspace_id)
    total = query.count()
    if after is not None:
        query = query.filter(id__gt=after)
    rows = list(query.order_by("id")[: PAGE_SIZE + 1])
    selected = rows[:PAGE_SIZE]
    return {
        "workspace_id": str(workspace_id),
        "total": total,
        "results": [
            {
                "id": str(plan.id),
                "timezone": plan.timezone,
                "local_time": plan.local_time.strftime("%H:%M"),
                "enabled": plan.enabled,
                "revision": plan.revision,
                "created_at": plan.created_at.isoformat(),
            }
            for plan in selected
        ],
        "next": str(selected[-1].id) if len(rows) > PAGE_SIZE else None,
    }
