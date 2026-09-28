import json
import sys

import vsn_lead_engine.cli as cli


def _config():
    return {
        "runtime":{
            "timezone":"Asia/Karachi",
            "mode":"free",
            "enabled":True,
            "daily_target_per_category":1000,
            "health_ledger_enabled":False,
            "process_watchdog_seconds":1560,
            "process_watchdog_kill_grace_seconds":20,
        },
        "registry":{"mode":"r2"},
        "categories":["A"],
    }


def test_supervised_scheduled_recovery_preserves_origin(monkeypatch,capsys):
    captured={}
    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setenv("VSN_RUN_ORIGIN","recovery-supervisor")

    def fake_supervise(command,*,timeout_seconds,kill_grace_seconds):
        captured["command"]=command
        captured["timeout_seconds"]=timeout_seconds
        captured["kill_grace_seconds"]=kill_grace_seconds
        return {
            "status":"completed",
            "exit_code":0,
            "timeout_seconds":timeout_seconds,
            "kill_grace_seconds":kill_grace_seconds,
            "runtime_seconds":1.0,
            "terminated":False,
            "killed":False,
        }

    monkeypatch.setattr(cli,"supervise_process",fake_supervise)
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "supervised-run",
        "--scheduled",
    ])

    assert cli.main()==0
    result=json.loads(capsys.readouterr().out)
    assert captured["command"][-2:]==["run","--scheduled"]
    assert result["origin"]=="recovery-supervisor"


def test_scheduled_run_preserves_recovery_origin_at_execution_gate(monkeypatch,capsys):
    captured={}
    config=_config()
    monkeypatch.setattr(cli,"load_config",lambda:config)
    monkeypatch.setenv("VSN_RUN_ORIGIN","recovery-supervisor")
    gate={
        "allowed":True,
        "status":"scheduled-window-open",
        "run_date":"2026-09-28",
        "local_time":"2026-09-28T23:30:00+05:00",
        "seconds_until_midnight":1800.0,
        "required_runway_seconds":1640.0,
    }
    monkeypatch.setattr(cli,"scheduled_run_window",lambda _config:gate)

    def fake_run(_config,*,origin,schedule):
        captured["origin"]=origin
        captured["schedule"]=schedule
        return 0,{
            "status":"complete",
            "run_date":"2026-09-28",
            "origin":origin,
        }

    monkeypatch.setattr(cli,"_run_with_incident_capture",fake_run)
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "run",
        "--scheduled",
    ])

    assert cli.main()==0
    result=json.loads(capsys.readouterr().out)
    assert captured["origin"]=="recovery-supervisor"
    assert captured["schedule"]==gate
    assert result["origin"]=="recovery-supervisor"


def test_scheduled_run_blocks_before_engine_when_midnight_runway_is_insufficient(
    monkeypatch,
    capsys,
):
    config=_config()
    monkeypatch.setattr(cli,"load_config",lambda:config)
    monkeypatch.setenv("VSN_RUN_ORIGIN","recovery-supervisor")
    monkeypatch.setattr(
        cli,
        "scheduled_run_window",
        lambda _config:{
            "allowed":False,
            "status":"scheduled-window-midnight-guard",
            "run_date":"2026-09-28",
            "local_time":"2026-09-28T23:40:00+05:00",
            "seconds_until_midnight":1200.0,
            "required_runway_seconds":1640.0,
            "block_reason":"insufficient-midnight-runway",
        },
    )
    monkeypatch.setattr(
        cli,
        "_run_with_incident_capture",
        lambda *_args,**_kwargs:(_ for _ in ()).throw(
            AssertionError("engine must not run")
        ),
    )
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "run",
        "--scheduled",
    ])

    assert cli.main()==0
    result=json.loads(capsys.readouterr().out)
    assert result["status"]=="scheduled-window-skipped"
    assert result["schedule"]["block_reason"]=="insufficient-midnight-runway"
