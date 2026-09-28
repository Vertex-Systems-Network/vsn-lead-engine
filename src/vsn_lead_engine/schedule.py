from __future__ import annotations

from datetime import date, datetime, timedelta
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
    allowed=start_hour <= hour <= end_hour

    return {
        "allowed":allowed,
        "status":"scheduled-window-open" if allowed else "scheduled-window-closed",
        "timezone":timezone,
        "run_date":local_now.date().isoformat(),
        "local_time":local_now.isoformat(),
        "window":{
            "start_hour":start_hour,
            "end_hour":end_hour,
        },
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
        try:
            target=date.fromisoformat(str(explicit_date).strip())
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
