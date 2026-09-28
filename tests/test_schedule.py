from pathlib import Path
from datetime import datetime, timezone

from vsn_lead_engine.schedule import scheduled_run_window


def config():
    return {
        "runtime":{
            "timezone":"Asia/Karachi",
            "start_hour":8,
            "end_hour":23,
        }
    }


def test_scheduled_window_opens_at_0800_pkt():
    result=scheduled_run_window(
        config(),
        now=datetime(2026,9,28,3,0,tzinfo=timezone.utc),
    )
    assert result["allowed"] is True
    assert result["run_date"]=="2026-09-28"
    assert result["slot"]=="2026-09-28T08:00"
    assert result["start_delay_minutes"]==0


def test_scheduled_window_allows_delayed_same_hour_catchup():
    result=scheduled_run_window(
        config(),
        now=datetime(2026,9,28,3,37,tzinfo=timezone.utc),
    )
    assert result["allowed"] is True
    assert result["local_time"].startswith("2026-09-28T08:37")
    assert result["start_delay_minutes"]==37
    assert result["shortfall_catchup"] is True


def test_scheduled_window_includes_2300_pkt():
    result=scheduled_run_window(
        config(),
        now=datetime(2026,9,28,18,59,tzinfo=timezone.utc),
    )
    assert result["allowed"] is True
    assert result["local_time"].startswith("2026-09-28T23:59")


def test_scheduled_window_rejects_after_midnight_instead_of_touching_next_day():
    result=scheduled_run_window(
        config(),
        now=datetime(2026,9,28,19,5,tzinfo=timezone.utc),
    )
    assert result["allowed"] is False
    assert result["run_date"]=="2026-09-29"
    assert result["status"]=="scheduled-window-closed"


def test_scheduled_window_rejects_before_0800_pkt():
    result=scheduled_run_window(
        config(),
        now=datetime(2026,9,28,2,59,tzinfo=timezone.utc),
    )
    assert result["allowed"] is False
    assert result["local_time"].startswith("2026-09-28T07:59")


def test_github_schedule_contract_matches_pkt_hourly_window():
    workflow=Path(".github/workflows/lead-engine.yml").read_text(encoding="utf-8")
    assert 'cron: "0 3-18 * * *"' in workflow
    assert "python -m vsn_lead_engine.cli supervised-run --scheduled" in workflow
    assert 'cron: "30 3-17 * * *"' not in workflow
