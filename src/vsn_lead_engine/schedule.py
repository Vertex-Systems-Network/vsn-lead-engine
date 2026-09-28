from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo


def scheduled_run_window(config: dict, *, now: datetime | None = None) -> dict:
    """Return a local-time gate for repo-native scheduled production runs."""
    runtime=config["runtime"]
    timezone=str(runtime.get("timezone","Asia/Karachi")).strip()
    zone=ZoneInfo(timezone)
    local_now=now or datetime.now(zone)
    if local_now.tzinfo is None:
        local_now=local_now.replace(tzinfo=zone)
    else:
        local_now=local_now.astimezone(zone)

    start_hour=int(runtime.get("start_hour",8))
    end_hour=int(runtime.get("end_hour",23))
    hour=local_now.hour
    within_hours=start_hour <= hour <= end_hour

    next_midnight=datetime.combine(
        local_now.date()+timedelta(days=1),
        datetime.min.time(),
        tzinfo=zone,
    )
    seconds_until_midnight=max(
        0.0,
        (next_midnight-local_now).total_seconds(),
    )
    watchdog_budget=(
        float(runtime.get("process_watchdog_seconds",1560))
        + float(runtime.get("process_watchdog_kill_grace_seconds",20))
    )
    event_budget=(
        float(runtime.get("event_wall_time_seconds",1500))
        + float(runtime.get("event_deadline_guard_seconds",60))
    )
    safety_seconds=max(
        0.0,
        float(runtime.get("schedule_midnight_safety_seconds",60)),
    )
    required_runway_seconds=max(watchdog_budget,event_budget)+safety_seconds
    midnight_safe=seconds_until_midnight >= required_runway_seconds
    allowed=within_hours and midnight_safe

    if not within_hours:
        status="scheduled-window-closed"
        block_reason="outside-hour-window"
    elif not midnight_safe:
        status="scheduled-window-midnight-guard"
        block_reason="insufficient-midnight-runway"
    else:
        status="scheduled-window-open"
        block_reason=None

    return {
        "allowed":allowed,
        "status":status,
        "timezone":timezone,
        "run_date":local_now.date().isoformat(),
        "local_time":local_now.isoformat(),
        "window":{
            "start_hour":start_hour,
            "end_hour":end_hour,
        },
        "within_hours":within_hours,
        "midnight_safe":midnight_safe,
        "seconds_until_midnight":round(seconds_until_midnight,3),
        "required_runway_seconds":round(required_runway_seconds,3),
        "safety_seconds":round(safety_seconds,3),
        "block_reason":block_reason,
        "slot":f"{local_now.date().isoformat()}T{hour:02d}:00",
        "start_delay_minutes":local_now.minute,
        "shortfall_catchup":allowed,
    }


def readiness_target_date(
    config: dict,
    *,
    now: datetime | None = None,
    explicit_date: str | None = None,
    next_day: bool = False,
) -> dict:
    """Resolve a bounded readiness target: local today or tomorrow only."""
    if explicit_date and next_day:
        raise ValueError("Use either explicit_date or next_day, not both.")

    runtime=config["runtime"]
    timezone=str(runtime.get("timezone","Asia/Karachi")).strip()
    zone=ZoneInfo(timezone)
    local_now=now or datetime.now(zone)
    if local_now.tzinfo is None:
        local_now=local_now.replace(tzinfo=zone)
    else:
        local_now=local_now.astimezone(zone)

    local_date=local_now.date()
    if explicit_date:
        raw_date=str(explicit_date).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",raw_date):
            raise ValueError("Readiness date must use YYYY-MM-DD format.")
        try:
            target=date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError("Readiness date must use YYYY-MM-DD format.") from exc
    else:
        target=local_date + timedelta(days=1 if next_day else 0)

    delta=(target-local_date).days
    if delta not in {0,1}:
        raise ValueError("Readiness target must be local today or tomorrow.")

    return {
        "run_date":target.isoformat(),
        "target_kind":"next-day" if delta==1 else "today",
        "timezone":timezone,
        "resolved_at":local_now.isoformat(),
    }
