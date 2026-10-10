"""Read-only, bounded diagnostic for daily schedule materialization candidates.

This deliberately does not authorize automatic dispatch, place jobs, lock rows,
open provider connections, or mutate schedule state. All findings are advisory.
"""

from datetime import UTC, timedelta
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import DailySchedule, Entitlement, Membership, ScheduleOccurrence
from .schedules import fingerprint, resolve_daily, validate_clock
from .serializers import SearchSerializer
from .services import membership_for

MAX_PAGE = 25


def due_plan_diagnostics(actor, workspace_id, *, now=None, limit=25, after=None):
    """Inspect at most 25 plans; pagination and calculations are read-only."""
    membership = membership_for(actor, workspace_id)
    if membership.role not in {"owner", "admin"}:
        raise PermissionDenied("Only workspace owners and admins can inspect scheduler status.")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise ValidationError("Daily plan diagnostic limit must be between 1 and 25.")
    if after is not None:
        try:
            after = UUID(str(after))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError("Invalid daily plan diagnostic cursor.") from None
    instant_now = now if now is not None else timezone.now()
    if instant_now.tzinfo is None or instant_now.utcoffset() is None:
        raise ValidationError("A timezone-aware diagnostic instant is required.")
    instant_now = instant_now.astimezone(UTC)
    query = DailySchedule.objects.filter(workspace_id=workspace_id)
    total = query.count()
    if after is not None:
        query = query.filter(id__gt=after)
    plans = list(query.order_by("id")[: limit + 1])
    selected = plans[:limit]
    # This is a snapshot hint only, not an authorization grant for execution.
    entitlement = Entitlement.objects.filter(workspace_id=workspace_id).first()
    entitlement_current = entitlement is not None and entitlement.is_current
    creator_ids = {p.created_by_id for p in selected if p.enabled}
    creator_roles = dict(
        Membership.objects.filter(workspace_id=workspace_id, user_id__in=creator_ids)
        .values_list("user_id", "role")
    )
    materialized = set(
        ScheduleOccurrence.objects.filter(
            schedule_id__in=[p.id for p in selected],
            local_date__gte=instant_now.date() - timedelta(days=8),
            local_date__lte=instant_now.date() + timedelta(days=2),
        ).values_list("schedule_id", "local_date")
    )
    results = []
    for plan in selected:
        entry = {"id": str(plan.id), "enabled": plan.enabled, "revision": plan.revision}
        if not plan.enabled:
            entry.update(status="disabled", due_local_dates=[])
            results.append(entry)
            continue
        try:
            zone = validate_clock(plan.timezone, plan.local_time)
            serializer = SearchSerializer(data=plan.search)
            if (
                not serializer.is_valid()
                or serializer.validated_data != plan.search
                or fingerprint(plan.search, plan.timezone, plan.local_time)
                != plan.request_hash
                or plan.revision < 1
            ):
                raise ValueError("Invalid stored schedule snapshot")
        except (ValidationError, ValueError, TypeError, AttributeError):
            entry.update(status="invalid_configuration", due_local_dates=[])
            results.append(entry)
            continue
        if creator_roles.get(plan.created_by_id) not in {"owner", "admin", "member"}:
            entry.update(status="creator_not_authorized", due_local_dates=[])
            results.append(entry)
            continue
        if not entitlement_current:
            entry.update(status="entitlement_not_current", due_local_dates=[])
            results.append(entry)
            continue
        today = instant_now.astimezone(zone).date()
        candidates = []
        for days_back in range(6, -1, -1):
            local_date = today - timedelta(days=days_back)
            if (plan.id, local_date) in materialized:
                continue
            scheduled_for, _, resolution = resolve_daily(
                plan.timezone, local_date, plan.local_time
            )
            if scheduled_for is None or scheduled_for <= instant_now:
                candidates.append(
                    {"local_date": local_date.isoformat(), "resolution": resolution}
                )
        entry.update(
            status="candidate_due_requires_execution_gates" if candidates else "no_unmaterialized_due_day",
            due_local_dates=candidates,
        )
        results.append(entry)
    return {
        "workspace_id": str(workspace_id),
        "as_of_utc": instant_now.isoformat(),
        "total_plans": total,
        "inspected": len(results),
        "next": str(selected[-1].id) if len(plans) > limit else None,
        "advisory_only": True,
        "requires_execution_gates": [
            "fresh_membership",
            "entitlement_capacity",
            "source_rights",
            "provider_credentials",
            "operator_release",
        ],
        "plans": results,
    }
