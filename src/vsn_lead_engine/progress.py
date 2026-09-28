from __future__ import annotations

from datetime import datetime, timezone
import json
import time


def emit_progress(
    event: str,
    *,
    enabled: bool = True,
    started_monotonic: float | None = None,
    **fields,
) -> dict | None:
    """Emit one compact, flushed, PII-free operational heartbeat."""
    if not enabled:
        return None

    payload = {
        "vsn_progress": 1,
        "event": str(event),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if started_monotonic is not None:
        payload["elapsed_seconds"] = round(
            max(0.0, time.monotonic() - float(started_monotonic)),
            3,
        )
    payload.update(fields)
    print(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
        flush=True,
    )
    return payload
