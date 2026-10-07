"""Explicit development accounting windows. No billing event or scheduled rollover."""

import re
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Entitlement, UsageCounter, UsagePeriod, UsageReservation, Workspace
from .services import IdempotencyConflict, membership_for
from .usage import COUNTERS


def active_window(counter, reservation=None):
    """Call under workspace lock before a new reservation/dispatch."""
    if reservation is not None and reservation.period_id != counter.period_id:
        raise ValidationError("Reservation accounting window no longer matches.")
    if counter.period_id is not None:
        period = counter.period
        now = timezone.now()
        if (
            period.workspace_id != counter.workspace_id
            or period.status != "open"
            or not period.starts_at <= now < period.ends_at
        ):
            raise PermissionDenied("Accounting window is unavailable or expired.")


@transaction.atomic
def advance_period(user, workspace_id, starts_at, ends_at, key):
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership = membership_for(user, workspace_id, lock=True)
    if membership.role not in {"owner", "admin"}:
        raise PermissionDenied(
            "Only current administrators may configure internal accounting windows."
        )
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValidationError("A bounded period key is required.")
    if not all(
        isinstance(value, datetime) and timezone.is_aware(value) for value in [starts_at, ends_at]
    ):
        raise ValidationError("Use timezone-aware accounting boundaries.")
    starts_at, ends_at = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
    if not timedelta(0) < ends_at - starts_at <= timedelta(days=366):
        raise ValidationError("Accounting windows must be positive and at most 366 days.")
    previous = UsagePeriod.objects.filter(workspace_id=workspace_id, key=key).first()
    if previous:
        if (previous.starts_at, previous.ends_at) != (starts_at, ends_at):
            raise IdempotencyConflict()
        return previous
    if not starts_at <= timezone.now() < ends_at:
        raise ValidationError("The new accounting window must contain the current time.")
    if not Entitlement.objects.filter(workspace_id=workspace_id, active=True).exists():
        raise PermissionDenied("Internal entitlement is inactive.")
    counter, _ = UsageCounter.objects.get_or_create(workspace_id=workspace_id)
    # Includes unknown/started and non-job reservations; never infer safe release.
    if UsageReservation.objects.filter(workspace_id=workspace_id, status="reserved").exists():
        raise ValidationError("Resolve all outstanding reservations before advancing periods.")
    if counter.period_id is None:
        if any(getattr(counter, name) for name in COUNTERS):
            raise ValidationError("Legacy cumulative usage requires an explicit migration plan.")
        if UsagePeriod.objects.filter(workspace_id=workspace_id).exists():
            raise ValidationError("Existing period history requires reconciliation.")
    else:
        current = UsagePeriod.objects.select_for_update().get(
            pk=counter.period_id, workspace_id=workspace_id
        )
        if (
            current.status != "open"
            or current.ends_at > timezone.now()
            or starts_at != current.ends_at
        ):
            raise ValidationError("Close only an expired window and continue its exact boundary.")
        current.status = "closed"
        current.closed_at = timezone.now()
        current.settled_snapshot = {name: getattr(counter, name) for name in COUNTERS}
        current.save(update_fields=["status", "closed_at", "settled_snapshot"])
    period = UsagePeriod.objects.create(
        workspace_id=workspace_id, key=key, starts_at=starts_at, ends_at=ends_at
    )
    counter.period = period
    for name in COUNTERS:
        setattr(counter, name, 0)
    counter.save(update_fields=["period", *COUNTERS])
    return period
