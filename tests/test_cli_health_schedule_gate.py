import json
import sys

import vsn_lead_engine.cli as cli


def _config():
    return {
        "runtime":{
            "timezone":"Asia/Karachi",
            "health_ledger_enabled":True,
        },
        "registry":{"mode":"r2"},
    }


def test_health_schedule_gate_records_blocked_decision(monkeypatch,capsys):
    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(
        cli,
        "scheduled_run_window",
        lambda _config:{
            "allowed":False,
            "status":"scheduled-window-midnight-guard",
            "run_date":"2026-09-28",
            "slot":"2026-09-28T23:00",
            "start_delay_minutes":50,
            "block_reason":"insufficient-midnight-runway",
            "midnight_safe":False,
            "within_hours":True,
            "seconds_until_midnight":600.0,
            "required_runway_seconds":1640.0,
            "safety_seconds":60.0,
        },
    )
    captured={}
    def fake_append(_config,run_date,event):
        captured["run_date"]=run_date
        captured["event"]=event
        return {"recorded":True,"status":"appended"}

    monkeypatch.setattr(cli,"_health_append",fake_append)
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "health-schedule-gate",
        "--origin",
        "recovery-supervisor",
    ])

    assert cli.main()==0
    payload=json.loads(capsys.readouterr().out)
    assert captured["run_date"]=="2026-09-28"
    assert captured["event"]["kind"]=="schedule-gate"
    assert captured["event"]["origin"]=="recovery-supervisor"
    assert captured["event"]["status"]=="blocked"
    assert captured["event"]["schedule_block_reason"]==(
        "insufficient-midnight-runway"
    )
    assert payload["health_ledger"]["recorded"] is True


def test_health_schedule_gate_returns_error_when_ledger_write_fails(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(
        cli,
        "scheduled_run_window",
        lambda _config:{
            "allowed":False,
            "status":"scheduled-window-closed",
            "run_date":"2026-09-28",
            "slot":"2026-09-28T07:00",
            "start_delay_minutes":0,
            "block_reason":"outside-hour-window",
            "midnight_safe":True,
            "within_hours":False,
            "seconds_until_midnight":61200.0,
            "required_runway_seconds":1640.0,
            "safety_seconds":60.0,
        },
    )
    monkeypatch.setattr(
        cli,
        "_health_append",
        lambda *_args,**_kwargs:{
            "recorded":False,
            "error":"R2Unavailable",
        },
    )
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "health-schedule-gate",
        "--origin",
        "recovery-supervisor",
    ])

    assert cli.main()==2
    payload=json.loads(capsys.readouterr().out)
    assert payload["event"]["status"]=="blocked"
    assert payload["health_ledger"]["recorded"] is False
