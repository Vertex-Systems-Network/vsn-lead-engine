import importlib.util
import json
import os
import stat
import sys
import urllib.parse
from pathlib import Path

import pytest


ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/google_oauth_onboard.py"


def _load_module():
    spec=importlib.util.spec_from_file_location("vsn_google_oauth_onboard",SCRIPT)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


def test_installed_client_loader_requires_desktop_shape(tmp_path):
    module=_load_module()
    path=tmp_path/"client.json"
    path.write_text(
        json.dumps({
            "installed":{
                "client_id":"client-id",
                "client_secret":"client-secret",
                "auth_uri":"https://accounts.example/auth",
                "token_uri":"https://accounts.example/token",
            }
        }),
        encoding="utf-8",
    )

    client=module.load_installed_client(path)

    assert client["client_id"]=="client-id"
    assert client["token_uri"]=="https://accounts.example/token"

    path.write_text(json.dumps({"web":{"client_id":"x"}}),encoding="utf-8")
    with pytest.raises(RuntimeError,match="Desktop app"):
        module.load_installed_client(path)


def test_authorization_url_uses_pkce_offline_consent_and_drive_scopes():
    module=_load_module()
    client={
        "client_id":"client-id",
        "client_secret":"client-secret",
        "auth_uri":"https://accounts.example/auth",
        "token_uri":"https://accounts.example/token",
    }
    url=module.authorization_url(
        client,
        redirect_uri="http://127.0.0.1:7777/",
        state_value="state-123",
        verifier="v"*64,
    )
    parsed=urllib.parse.urlparse(url)
    query=urllib.parse.parse_qs(parsed.query)

    assert query["access_type"]==["offline"]
    assert query["prompt"]==["consent"]
    assert query["code_challenge_method"]==["S256"]
    assert query["state"]==["state-123"]
    assert query["redirect_uri"]==["http://127.0.0.1:7777/"]
    assert set(query["scope"][0].split())==set(module.GOOGLE_SCOPES)


def test_exchange_code_returns_only_authorized_user_secret_surface():
    module=_load_module()
    captured={}

    def fake_post(url,data):
        captured["url"]=url
        captured["data"]=dict(data)
        return {
            "access_token":"short-lived",
            "refresh_token":"refresh-secret",
            "expires_in":3600,
        }

    payload=module.exchange_code(
        {
            "client_id":"client-id",
            "client_secret":"client-secret",
            "auth_uri":"https://accounts.example/auth",
            "token_uri":"https://accounts.example/token",
        },
        code="auth-code",
        redirect_uri="http://127.0.0.1:7777/",
        verifier="verifier",
        post=fake_post,
    )

    assert payload["type"]=="authorized_user"
    assert payload["refresh_token"]=="refresh-secret"
    assert "access_token" not in payload
    assert captured["data"]["grant_type"]=="authorization_code"
    assert captured["data"]["code_verifier"]=="verifier"


def test_exchange_requires_refresh_token():
    module=_load_module()

    with pytest.raises(RuntimeError,match="refresh token"):
        module.exchange_code(
            {
                "client_id":"client-id",
                "client_secret":"client-secret",
                "auth_uri":"https://accounts.example/auth",
                "token_uri":"https://accounts.example/token",
            },
            code="auth-code",
            redirect_uri="http://127.0.0.1:7777/",
            verifier="verifier",
            post=lambda _url,_data:{"access_token":"only-short-lived"},
        )


def test_secret_writer_uses_compact_json_and_private_permissions(tmp_path):
    module=_load_module()
    path=tmp_path/"oauth.json"
    payload={
        "type":"authorized_user",
        "client_id":"client",
        "client_secret":"secret",
        "refresh_token":"refresh",
        "token_uri":"https://oauth2.googleapis.com/token",
        "scopes":module.GOOGLE_SCOPES,
    }

    module.write_authorized_user(path,payload)

    assert json.loads(path.read_text(encoding="utf-8"))==payload
    if os.name!="nt":
        mode=stat.S_IMODE(path.stat().st_mode)
        assert mode==0o600
