from __future__ import annotations

from datetime import datetime
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
