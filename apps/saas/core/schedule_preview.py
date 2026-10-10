"""Read-only daily local-time/DST preview. Never creates or enables a schedule."""

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .schedules import resolve_daily, validate_clock


class DailyTimePreviewForm(forms.Form):
    timezone = forms.CharField(max_length=64, label="IANA timezone")
    time = forms.TimeField(
        input_formats=["%H:%M"],
        label="Daily local time",
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )

    def clean(self):
        cleaned = super().clean()
        if "timezone" in cleaned and "time" in cleaned:
            try:
                validate_clock(cleaned["timezone"], cleaned["time"])
            except ValidationError as exc:
                raise forms.ValidationError(
                    "Choose a valid IANA timezone and local HH:MM."
                ) from exc
        return cleaned


def upcoming_daily_preview(zone_name, local_time, *, now=None):
    """Next three local-day decisions, using existing earliest-fold/gap-forward policy."""
    zone = validate_clock(zone_name, local_time)
    instant_now = now if now is not None else timezone.now()
    local_today = instant_now.astimezone(zone).date()
    today_utc, _, _ = resolve_daily(zone_name, local_today, local_time)
    first_date = (
        local_today
        if today_utc is not None and today_utc > instant_now
        else local_today + timedelta(days=1)
    )
    decisions = []
    for index in range(3):
        local_date = first_date + timedelta(days=index)
        instant, offset, resolution = resolve_daily(zone_name, local_date, local_time)
        if instant is None:
            decisions.append(
                {
                    "local_date": local_date.isoformat(),
                    "resolved_local_time": "No valid local time",
                    "utc_instant": "No run on skipped civil day",
                    "offset": "Unavailable",
                    "resolution": resolution,
                }
            )
            continue
        local = instant.astimezone(ZoneInfo(zone_name))
        magnitude = abs(offset)
        hours, remainder = divmod(magnitude, 3600)
        minutes = remainder // 60
        decisions.append(
            {
                "local_date": local_date.isoformat(),
                "resolved_local_time": local.strftime("%H:%M"),
                "utc_instant": instant.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                "offset": f"UTC{'+' if offset >= 0 else '-'}{hours:02d}:{minutes:02d}",
                "resolution": resolution,
            }
        )
    return decisions
