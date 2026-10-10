"""Bounded internal daily draft materialization. No timer, enqueue or external work."""

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, revision
from .models import DailySchedule, Entitlement, ScheduleOccurrence
from .serializers import SearchSerializer
from .services import IdempotencyConflict, create_draft, membership_for
from .usage import lock_workspace


def validate_clock(zone_name, local_time):
    if not isinstance(zone_name, str) or len(zone_name) > 64:
        raise ValidationError("Choose a bounded IANA timezone.")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Choose a valid IANA timezone.") from None
    if (
        not isinstance(local_time, time)
        or local_time.tzinfo is not None
        or local_time.second
        or local_time.microsecond
    ):
        raise ValidationError("Use a local hour/minute without a UTC offset.")
    return zone


def fingerprint(search, zone_name, local_time):
    payload = {"search": search, "timezone": zone_name, "local_time": local_time.isoformat()}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def resolve_daily(zone_name, local_date, local_time):
    """M3 policy: earliest fold; first valid minute in the same local day for gaps."""
    zone = validate_clock(zone_name, local_time)
    if type(local_date) is not date:
        raise ValidationError("Use a local calendar date.")
    requested = datetime.combine(local_date, local_time)
    for minute in range(1440 - local_time.hour * 60 - local_time.minute):
        candidate = requested + timedelta(minutes=minute)
        if candidate.date() != local_date:
            break
        instants = set()
        for fold in (0, 1):
            instant = candidate.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if instant.astimezone(zone).replace(tzinfo=None) == candidate:
                instants.add(instant)
        if instants:
            instant = min(instants)
            resolution = (
                "gap_forward" if minute else "ambiguous_earlier" if len(instants) > 1 else "normal"
            )
            offset = int(instant.astimezone(zone).utcoffset().total_seconds())
            return instant, offset, resolution
    # A whole civil date can be removed by a zone change; never shift to another day.
    return None, None, "skipped_day"


@transaction.atomic
def create_daily_schedule(user, workspace_id, search, zone_name, local_time, key):
    lock_workspace(user, workspace_id)
    validate_clock(zone_name, local_time)
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValidationError("A bounded schedule key is required.")
    serializer = SearchSerializer(data=search)
    serializer.is_valid(raise_exception=True)
    search = serializer.validated_data
    request_hash = fingerprint(search, zone_name, local_time)
    previous = DailySchedule.objects.filter(workspace_id=workspace_id, key=key).first()
    if previous:
        if previous.request_hash != request_hash:
            raise IdempotencyConflict()
        return previous, False
    return DailySchedule.objects.create(
        workspace_id=workspace_id,
        created_by=user,
        key=key,
        timezone=zone_name,
        local_time=local_time,
        search=search,
        request_hash=request_hash,
        enabled=False,  # Human-authored plans cannot schedule or dispatch work.
    ), True


@transaction.atomic
def materialize_daily(user, workspace_id, schedule_id, local_date, expected_revision):
    """At most one due draft per call, seven local dates maximum catch-up; no capacity claim."""
    expected_revision = revision(expected_revision)
    lock_workspace(user, workspace_id)
    schedule = (
        DailySchedule.objects.select_for_update()
        .filter(pk=schedule_id, workspace_id=workspace_id)
        .first()
    )
    if schedule is None:
        raise Http404("Workspace resource not found.")
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    creator = membership_for(schedule.created_by_id, workspace_id, lock=True)
    if creator.role not in {"owner", "admin", "member"}:
        raise PermissionDenied("Schedule creator no longer has job-write permission.")
    if not schedule.enabled or schedule.revision != expected_revision:
        raise RevisionConflict()
    serializer = SearchSerializer(data=schedule.search)
    serializer.is_valid(raise_exception=True)
    if (
        serializer.validated_data != schedule.search
        or fingerprint(schedule.search, schedule.timezone, schedule.local_time)
        != schedule.request_hash
    ):
        raise ValidationError("Stored schedule configuration needs reconciliation.")
    validate_clock(schedule.timezone, schedule.local_time)
    if type(local_date) is not date:
        raise ValidationError("Use a local calendar date.")
    previous = ScheduleOccurrence.objects.filter(schedule=schedule, local_date=local_date).first()
    if previous:
        if (
            previous.schedule_revision != expected_revision
            or previous.request_hash != schedule.request_hash
            or previous.local_time != schedule.local_time
            or previous.timezone != schedule.timezone
        ):
            raise RevisionConflict()
        return previous, False
    now = timezone.now()
    today = now.astimezone(ZoneInfo(schedule.timezone)).date()
    if not today - timedelta(days=6) <= local_date <= today:
        raise ValidationError(
            "Only due occurrences within the last seven local dates may materialize."
        )
    instant, offset, resolution = resolve_daily(schedule.timezone, local_date, schedule.local_time)
    if instant and instant > now:
        raise ValidationError("The requested local occurrence is not due yet.")
    job = None
    if instant is not None:
        key = f"schedule:{schedule.id}:{schedule.revision}:{local_date.isoformat()}T{schedule.local_time.isoformat()}"
        # Use the originating member, rechecked under the same workspace lock.
        job, created = create_draft(schedule.created_by, workspace_id, schedule.search, key)
        if not created:
            raise IdempotencyConflict()
    occurrence = ScheduleOccurrence.objects.create(
        schedule=schedule,
        workspace_id=workspace_id,
        schedule_revision=schedule.revision,
        local_date=local_date,
        local_time=schedule.local_time,
        timezone=schedule.timezone,
        request_hash=schedule.request_hash,
        scheduled_for=instant,
        utc_offset_seconds=offset,
        resolution=resolution,
        job=job,
    )
    return occurrence, True
