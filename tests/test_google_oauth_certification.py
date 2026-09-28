import json
import sys

import vsn_lead_engine.cli as cli


class _FakeStore:
    def __init__(self,_config,run_date=None,auth_mode="service-account"):
        self.run_date=run_date
        self.google_auth_mode=auth_mode
        self.probe_calls=0

    def drive_creation_capability(self,*,probe_create=False):
        self.probe_calls+=1
        return {
            "status":"capable",
            "auth_mode":self.google_auth_mode,
            "probe_performed":bool(probe_create),
            "probe_cleaned":bool(probe_create),
        }


def _config():
    return {
        "runtime":{
            "timezone":"Asia/Karachi",
            "mode":"free",
            "enabled":True,
            "daily_target_per_category":1000,
        },
        "registry":{"mode":"r2"},
        "categories":["A"],
    }


def test_capability_cli_strict_oauth_blocks_service_account(monkeypatch,capsys):
    holder={}

    class FakeStore(_FakeStore):
        def __init__(self,config,run_date=None):
            super().__init__(config,run_date,auth_mode="service-account")
            holder["store"]=self

    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(cli,"GoogleSheetsStore",FakeStore)
    monkeypatch.setattr(
        cli,
        "readiness_target_date",
        lambda *_args,**_kwargs:{
            "run_date":"2026-09-29",
            "target_kind":"next-day",
            "resolved_at":"2026-09-28T23:00:00+05:00",
        },
    )
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "google-drive-capability",
        "--next-day",
        "--require-user-oauth",
        "--probe-create",
    ])

    assert cli.main()==2
    data=json.loads(capsys.readouterr().out)
    assert data["status"]=="blocked"
    assert data["permanent"] is True
    assert data["auth_mode"]=="service-account"
    assert data["probe_performed"] is False
    assert "GOOGLE_OAUTH_USER_JSON" in data["reason"]
    assert holder["store"].probe_calls==0


def test_capability_cli_strict_oauth_allows_user_probe(monkeypatch,capsys):
    class FakeStore(_FakeStore):
        def __init__(self,config,run_date=None):
            super().__init__(config,run_date,auth_mode="user-oauth")

    monkeypatch.setattr(cli,"load_config",lambda:_config())
    monkeypatch.setattr(cli,"GoogleSheetsStore",FakeStore)
    monkeypatch.setattr(
        cli,
        "readiness_target_date",
        lambda *_args,**_kwargs:{
            "run_date":"2026-09-29",
            "target_kind":"next-day",
            "resolved_at":"2026-09-28T23:00:00+05:00",
        },
    )
    monkeypatch.setattr(sys,"argv",[
        "vsn-lead-engine",
        "google-drive-capability",
        "--next-day",
        "--require-user-oauth",
        "--probe-create",
    ])

    assert cli.main()==0
    data=json.loads(capsys.readouterr().out)
    assert data["status"]=="capable"
    assert data["auth_mode"]=="user-oauth"
    assert data["probe_performed"] is True
    assert data["probe_cleaned"] is True


def test_capability_workflow_requires_secret_and_strict_oauth():
    content=open(
        ".github/workflows/google-drive-capability.yml",
        encoding="utf-8",
    ).read()

    assert 'test -n "$GOOGLE_OAUTH_USER_JSON"' in content
    assert "Autonomous My Drive creation cannot be certified." in content
    assert "--require-user-oauth" in content
    assert "--probe-create" in content
