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


def test_recovery_supervisor_dispatches_only_bounded_shortfall_runs():
    supervisor=Path(".github/workflows/quota-recovery-supervisor.yml").read_text(
        encoding="utf-8"
    )
    lead_workflow=Path(".github/workflows/lead-engine.yml").read_text(
        encoding="utf-8"
    )

    assert 'workflows: ["Lead Engine"]' in supervisor
    assert 'cron: "*/10 3-18 * * *"' in supervisor
    assert "actions: write" in supervisor
    assert "github.event_name == 'schedule'" in supervisor
    assert "github.event.workflow_run.event != 'pull_request'" in supervisor
    assert "workbook-ready-recover --attempts 3 --delay-seconds 20" in supervisor
    assert '.head_branch == "main"' in supervisor
    assert '.event != "pull_request"' in supervisor
    assert '.status == "waiting"' in supervisor
    assert '.status == "requested"' in supervisor
    assert '.status == "pending"' in supervisor
    assert "gh workflow run lead-engine.yml" in supervisor
    assert "-f run_origin=recovery-supervisor" in supervisor
    assert "recovery_supervisor_enabled" in supervisor
    assert "run_origin:" in lead_workflow
    assert "VSN_RUN_ORIGIN: ${{ inputs.run_origin }}" in lead_workflow


def test_readiness_target_defaults_to_local_today():
    from vsn_lead_engine.schedule import readiness_target_date

    result=readiness_target_date(
        config(),
        now=datetime(2026,9,28,15,30,tzinfo=timezone.utc),
    )

    assert result["run_date"]=="2026-09-28"
    assert result["target_kind"]=="today"
    assert result["resolved_at"].startswith("2026-09-28T20:30")


def test_readiness_target_next_day_uses_local_tomorrow():
    from vsn_lead_engine.schedule import readiness_target_date

    result=readiness_target_date(
        config(),
        now=datetime(2026,9,28,15,50,tzinfo=timezone.utc),
        next_day=True,
    )

    assert result["run_date"]=="2026-09-29"
    assert result["target_kind"]=="next-day"
    assert result["resolved_at"].startswith("2026-09-28T20:50")


def test_readiness_target_accepts_explicit_tomorrow_only():
    from vsn_lead_engine.schedule import readiness_target_date

    result=readiness_target_date(
        config(),
        now=datetime(2026,9,28,12,0,tzinfo=timezone.utc),
        explicit_date="2026-09-29",
    )
    assert result["run_date"]=="2026-09-29"
    assert result["target_kind"]=="next-day"


def test_readiness_target_rejects_historical_or_far_future_dates():
    import pytest
    from vsn_lead_engine.schedule import readiness_target_date

    now=datetime(2026,9,28,12,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match="today or tomorrow"):
        readiness_target_date(config(),now=now,explicit_date="2026-09-27")
    with pytest.raises(ValueError,match="today or tomorrow"):
        readiness_target_date(config(),now=now,explicit_date="2026-09-30")


def test_readiness_target_rejects_ambiguous_date_flags():
    import pytest
    from vsn_lead_engine.schedule import readiness_target_date

    with pytest.raises(ValueError,match="either explicit_date or next_day"):
        readiness_target_date(
            config(),
            explicit_date="2026-09-29",
            next_day=True,
        )


def test_daily_readiness_workflow_has_evening_next_day_and_morning_recovery():
    workflow=Path(".github/workflows/daily-workbook-readiness.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "50 15 * * *"' in workflow
    assert 'cron: "50 2 * * *"' in workflow
    assert 'target_day:' in workflow
    assert 'next-day' in workflow
    assert 'args+=(--next-day)' in workflow
    assert 'workbook-ready-recover' in workflow
    assert '--attempts 3' in workflow
    assert '--delay-seconds 60' in workflow


def test_readiness_target_rejects_non_iso_basic_format():
    import pytest
    from vsn_lead_engine.schedule import readiness_target_date

    with pytest.raises(ValueError,match="YYYY-MM-DD"):
        readiness_target_date(
            config(),
            now=datetime(2026,9,28,12,0,tzinfo=timezone.utc),
            explicit_date="20260929",
        )


def test_daily_readiness_workflow_has_main_deployment_catchup_scope():
    workflow=Path(".github/workflows/daily-workbook-readiness.yml").read_text(
        encoding="utf-8"
    )

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    for path in [
        ".github/workflows/daily-workbook-readiness.yml",
        "src/vsn_lead_engine/cli.py",
        "src/vsn_lead_engine/schedule.py",
        "src/vsn_lead_engine/health.py",
        "src/vsn_lead_engine/engine.py",
        "src/vsn_lead_engine/sheets.py",
    ]:
        assert f'- "{path}"' in workflow

    assert 'if [[ "$EVENT_NAME" == "push" ]]; then' in workflow
    assert 'target="next-day"' in workflow
    assert "README.md" not in workflow
