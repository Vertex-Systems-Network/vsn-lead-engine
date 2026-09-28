import json
from pathlib import Path

import pytest

import vsn_lead_engine.sheets as sheets


class _FakeUserCredentials:
    calls=[]

    @classmethod
    def from_authorized_user_info(cls,info,scopes=None):
        cls.calls.append((info,list(scopes or [])))
        return "oauth-creds"


class _FakeServiceCredentials:
    calls=[]

    @classmethod
    def from_service_account_info(cls,info,scopes=None):
        cls.calls.append((info,list(scopes or [])))
        return "service-creds"


def test_google_auth_mode_prefers_user_oauth(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_OAUTH_USER_JSON",
        json.dumps({
            "type":"authorized_user",
            "client_id":"client",
            "client_secret":"secret",
            "refresh_token":"refresh",
        }),
    )
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        json.dumps({"type":"service_account"}),
    )
    monkeypatch.setattr(sheets,"UserCredentials",_FakeUserCredentials)

    credentials,mode=sheets.google_credentials_from_env()

    assert mode=="user-oauth"
    assert credentials=="oauth-creds"
    assert sheets.google_auth_mode_from_env()=="user-oauth"
    assert _FakeUserCredentials.calls[-1][0]["refresh_token"]=="refresh"
    assert set(_FakeUserCredentials.calls[-1][1])==set(sheets.GOOGLE_SCOPES)


def test_google_auth_falls_back_to_service_account(monkeypatch):
    _FakeServiceCredentials.calls.clear()
    monkeypatch.delenv("GOOGLE_OAUTH_USER_JSON",raising=False)
    monkeypatch.setenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        json.dumps({
            "type":"service_account",
            "client_email":"svc@example.invalid",
        }),
    )
    monkeypatch.setattr(
        sheets.service_account,
        "Credentials",
        _FakeServiceCredentials,
    )

    credentials,mode=sheets.google_credentials_from_env()

    assert mode=="service-account"
    assert credentials=="service-creds"
    assert sheets.google_auth_mode_from_env()=="service-account"
    assert _FakeServiceCredentials.calls[-1][0]["client_email"]=="svc@example.invalid"


def test_google_auth_missing_credentials_fails_closed(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_USER_JSON",raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON",raising=False)

    assert sheets.google_auth_mode_from_env()=="missing"
    with pytest.raises(RuntimeError,match="Google credentials are required"):
        sheets.google_credentials_from_env()


def test_google_oauth_rejects_wrong_credential_type(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_OAUTH_USER_JSON",
        json.dumps({"type":"service_account"}),
    )
    with pytest.raises(RuntimeError,match="authorized-user"):
        sheets.google_credentials_from_env()


def test_google_write_workflows_expose_oauth_and_service_account_secrets():
    workflows=[
        "lead-engine.yml",
        "daily-workbook-readiness.yml",
        "quota-recovery-supervisor.yml",
        "registry-maintenance.yml",
        "r2-registry.yml",
    ]
    root=Path(".github/workflows")
    for name in workflows:
        content=(root/name).read_text(encoding="utf-8")
        assert "GOOGLE_OAUTH_USER_JSON: ${{ secrets.GOOGLE_OAUTH_USER_JSON }}" in content, name
        assert "GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}" in content, name


def test_workflow_credential_gates_accept_either_auth_mode():
    root=Path(".github/workflows")
    lead=(root/"lead-engine.yml").read_text(encoding="utf-8")
    supervisor=(root/"quota-recovery-supervisor.yml").read_text(encoding="utf-8")
    maintenance=(root/"registry-maintenance.yml").read_text(encoding="utf-8")

    either='[ -n "$GOOGLE_OAUTH_USER_JSON" ] || [ -n "$GOOGLE_SERVICE_ACCOUNT_JSON" ]'
    assert either in lead
    assert either in supervisor
    assert 'test -n "$GOOGLE_OAUTH_USER_JSON" || test -n "$GOOGLE_SERVICE_ACCOUNT_JSON"' in maintenance
