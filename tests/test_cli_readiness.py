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
            "health_ledger_enabled":True,
        },
        "registry":{"mode":"r2"},
        "categories":["A"],
    }


def test_workbook_ready_next_day_passes_resolved_date(monkeypatch,capsys):
    captured={}
    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(
        cli,
        "readiness_target_date",
        lambda *_args,**_kwargs:{
            "run_date":"2026-09-29",
            "target_kind":"next-day",
            "resolved_at":"2026-09-28T20:50:00+05:00",
        },
    )

    def fake_check(_config,*,run_date):
        captured["run_date"]=run_date
        return {
            "status":"ready",
            "run_date":run_date,
            "workbook":{"id":"sheet","name":"Tomorrow"},
            "counts":{"A":0},
            "country_counts":{"United States":0,"Canada":0},
            "quota_complete":False,
        }

    monkeypatch.setattr(cli,"check_workbook_readiness",fake_check)
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "workbook-ready",
        "--next-day",
    ])

    assert cli.main()==0
    data=json.loads(capsys.readouterr().out)
    assert captured["run_date"]=="2026-09-29"
    assert data["target_kind"]=="next-day"
    assert data["target_resolved_at"]=="2026-09-28T20:50:00+05:00"


def test_workbook_ready_recover_next_day_records_target_health(monkeypatch,capsys):
    captured={}
    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(
        cli,
        "readiness_target_date",
        lambda *_args,**_kwargs:{
            "run_date":"2026-09-29",
            "target_kind":"next-day",
            "resolved_at":"2026-09-28T20:50:00+05:00",
        },
    )

    def fake_recover(_config,*,run_date,attempts,delay_seconds):
        captured["recover"]=(run_date,attempts,delay_seconds)
        return {
            "status":"recovered",
            "run_date":run_date,
            "attempts_used":2,
            "attempts_configured":3,
            "retry_delay_seconds":60,
            "failures":[],
            "quota_complete":False,
        }

    def fake_health(_config,run_date,event):
        captured["health_date"]=run_date
        captured["health_event"]=event
        return {"recorded":True,"status":"appended"}

    monkeypatch.setattr(cli,"recover_workbook_readiness",fake_recover)
    monkeypatch.setattr(cli,"_health_append",fake_health)
    monkeypatch.setattr(cli,"readiness_health_event",lambda result:{"status":result["status"]})
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "workbook-ready-recover",
        "--next-day",
        "--attempts","3",
        "--delay-seconds","60",
        "--record-health",
    ])

    assert cli.main()==0
    data=json.loads(capsys.readouterr().out)
    assert captured["recover"]==("2026-09-29",3,60.0)
    assert captured["health_date"]=="2026-09-29"
    assert data["target_kind"]=="next-day"
    assert data["health_ledger"]["recorded"] is True
