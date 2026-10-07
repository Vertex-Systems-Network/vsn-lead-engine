"""Internal transactional budget services. No queue/provider/payment side effects."""

import hashlib
import json
import re

from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Entitlement, JobOutbox, UsageCounter, UsageReservation, Workspace
from .services import IdempotencyConflict, membership_for

COUNTERS = {
    "leads": "lead_limit",
    "jobs": "job_limit",
    "provider_calls": "provider_call_limit",
    "exports": "export_limit",
}


def amounts(values):
    if not isinstance(values, dict) or set(values) - set(COUNTERS):
        raise ValidationError("Unsupported usage counters.")
    result = {}
    for name in COUNTERS:
        value = values.get(name, 0)
        if type(value) is not int or value < 0 or value > 2147483647:
            raise ValidationError("Usage must be bounded nonnegative integers.")
        result[name] = value
    return result


def lock_workspace(user, workspace_id):
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership = membership_for(user, workspace_id, lock=True)
    if membership.role not in {"owner", "admin", "member"}:
        raise PermissionDenied("This role cannot reserve usage.")


@transaction.atomic
def reserve_usage(user, workspace_id, key, requested):
    requested = amounts(requested)
    if not key or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValidationError("A valid reservation key is required.")
    lock_workspace(user, workspace_id)
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.active:
        raise PermissionDenied("Workspace entitlement is inactive.")
    request_hash = hashlib.sha256(json.dumps(requested, sort_keys=True).encode()).hexdigest()
    previous = UsageReservation.objects.filter(workspace_id=workspace_id, key=key).first()
    if previous:
        if previous.request_hash != request_hash:
            raise IdempotencyConflict()
        return previous
    counter, _ = UsageCounter.objects.get_or_create(workspace_id=workspace_id)
    from .periods import active_window

    active_window(counter)
    pending = UsageReservation.objects.filter(
        workspace_id=workspace_id, status="reserved"
    ).aggregate(**{name: Sum(name) for name in COUNTERS})
    for name, limit in COUNTERS.items():
        if getattr(counter, name) + (pending[name] or 0) + requested[name] > getattr(
            entitlement, limit
        ):
            raise ValidationError(f"{name} budget exceeded.")
    return UsageReservation.objects.create(
        workspace_id=workspace_id,
        period_id=counter.period_id,
        key=key,
        request_hash=request_hash,
        **requested,
    )


@transaction.atomic
def settle_usage(user, workspace_id, reservation_id, actual):
    actual = amounts(actual)
    lock_workspace(user, workspace_id)
    reservation = (
        UsageReservation.objects.select_for_update()
        .filter(workspace_id=workspace_id, id=reservation_id)
        .first()
    )
    if reservation is None:
        raise Http404("Workspace resource not found.")
    if JobOutbox.objects.filter(reservation=reservation).exists():
        raise ValidationError("Job usage must finalize through job reconciliation.")
    return _settle_locked(reservation, actual)


def _settle_locked(reservation, actual):
    """Private primitive: caller holds workspace and reservation locks in a transaction."""
    workspace_id = reservation.workspace_id
    actual = amounts(actual)
    if reservation.status == "settled":
        if reservation.settlement != actual:
            raise IdempotencyConflict()
        return reservation
    if reservation.status != "reserved":
        raise ValidationError("Released reservations cannot settle.")
    if any(actual[name] > getattr(reservation, name) for name in COUNTERS):
        raise ValidationError("Actual usage cannot exceed reserved usage.")
    counter, _ = UsageCounter.objects.get_or_create(workspace_id=workspace_id)
    if counter.period_id != reservation.period_id:
        raise ValidationError("Reservation accounting window no longer matches.")
    for name in COUNTERS:
        setattr(counter, name, getattr(counter, name) + actual[name])
    counter.save(update_fields=list(COUNTERS))
    reservation.status = "settled"
    reservation.settlement = actual
    reservation.save(update_fields=["status", "settlement", "updated_at"])
    return reservation


@transaction.atomic
def release_usage(user, workspace_id, reservation_id):
    lock_workspace(user, workspace_id)
    reservation = (
        UsageReservation.objects.select_for_update()
        .filter(workspace_id=workspace_id, id=reservation_id)
        .first()
    )
    if reservation is None:
        raise Http404("Workspace resource not found.")
    if JobOutbox.objects.filter(reservation=reservation).exists():
        raise ValidationError(
            "Job usage must release through pending cancellation or reconciliation."
        )
    return _release_locked(reservation)


def _release_locked(reservation):
    """Private primitive: caller holds workspace and reservation locks in a transaction."""
    if reservation.status == "settled":
        raise ValidationError("Settled usage cannot be refunded through release.")
    if reservation.status == "reserved":
        reservation.status = "released"
        reservation.save(update_fields=["status", "updated_at"])
    return reservation
