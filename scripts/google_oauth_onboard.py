from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


DEFAULT_AUTH_URI="https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_URI="https://oauth2.googleapis.com/token"


def load_installed_client(path: Path) -> dict:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read OAuth client JSON: {path}") from exc
    installed=data.get("installed") if isinstance(data,dict) else None
    if not isinstance(installed,dict):
        raise RuntimeError(
            "OAuth client JSON must be a Google Desktop app credential "
            "with an 'installed' object."
        )
    required=["client_id","client_secret"]
    missing=[key for key in required if not str(installed.get(key) or "").strip()]
    if missing:
        raise RuntimeError(
            "OAuth Desktop client is missing: " + ", ".join(missing)
        )
    return {
        "client_id":str(installed["client_id"]).strip(),
        "client_secret":str(installed["client_secret"]).strip(),
        "auth_uri":str(installed.get("auth_uri") or DEFAULT_AUTH_URI).strip(),
        "token_uri":str(installed.get("token_uri") or DEFAULT_TOKEN_URI).strip(),
    }


def code_verifier() -> str:
    return secrets.token_urlsafe(72)


def code_challenge(verifier: str) -> str:
    digest=hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorization_url(
    client: dict,
    *,
    redirect_uri: str,
    state_value: str,
    verifier: str,
) -> str:
    query=urllib.parse.urlencode({
        "client_id":client["client_id"],
        "redirect_uri":redirect_uri,
        "response_type":"code",
        "scope":" ".join(GOOGLE_SCOPES),
        "access_type":"offline",
        "prompt":"consent",
        "include_granted_scopes":"true",
        "state":state_value,
        "code_challenge":code_challenge(verifier),
        "code_challenge_method":"S256",
    })
    return f"{client['auth_uri']}?{query}"


def _post_form_json(url: str, data: dict) -> dict:
    encoded=urllib.parse.urlencode(data).encode("utf-8")
    request=urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type":"application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request,timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def exchange_code(
    client: dict,
    *,
    code: str,
    redirect_uri: str,
    verifier: str,
    post=None,
) -> dict:
    payload=(post or _post_form_json)(
        client["token_uri"],
        {
            "code":code,
            "client_id":client["client_id"],
            "client_secret":client["client_secret"],
            "redirect_uri":redirect_uri,
            "grant_type":"authorization_code",
            "code_verifier":verifier,
        },
    )
    refresh_token=str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. Re-run the onboarding flow "
            "with consent and verify the OAuth app is a Desktop application."
        )
    return {
        "type":"authorized_user",
        "client_id":client["client_id"],
        "client_secret":client["client_secret"],
        "refresh_token":refresh_token,
        "token_uri":client["token_uri"],
        "scopes":GOOGLE_SCOPES,
    }


def write_authorized_user(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps(payload,separators=(",",":"))+"\n",
        encoding="utf-8",
    )
    try:
        path.chmod(stat.S_IRUSR|stat.S_IWUSR)
    except OSError:
        pass


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed=urllib.parse.urlparse(self.path)
        params=urllib.parse.parse_qs(parsed.query)
        self.server.oauth_result={
            "code":str((params.get("code") or [""])[0]),
            "state":str((params.get("state") or [""])[0]),
            "error":str((params.get("error") or [""])[0]),
        }
        body=(
            "VSN Lead Engine Google OAuth authorization received. "
            "You can close this browser tab."
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/plain; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def main() -> int:
    parser=argparse.ArgumentParser(
        description=(
            "Create a local Google authorized-user JSON for VSN Lead Engine. "
            "Refresh/access tokens are never printed to stdout."
        )
    )
    parser.add_argument("client_json",type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".google-oauth-user.json"),
    )
    parser.add_argument("--timeout-seconds",type=int,default=300)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the authorization URL instead of opening a browser.",
    )
    args=parser.parse_args()

    client=load_installed_client(args.client_json)
    verifier=code_verifier()
    state_value=secrets.token_urlsafe(32)

    server=HTTPServer(("127.0.0.1",0),OAuthCallbackHandler)
    server.oauth_result={}
    server.timeout=max(30,min(900,int(args.timeout_seconds)))
    redirect_uri=f"http://127.0.0.1:{server.server_port}/"
    url=authorization_url(
        client,
        redirect_uri=redirect_uri,
        state_value=state_value,
        verifier=verifier,
    )

    if args.no_browser:
        print("Open this Google authorization URL in your browser:")
        print(url)
    else:
        opened=webbrowser.open(url,new=1,autoraise=True)
        if not opened:
            print("Browser did not open automatically. Open this URL:")
            print(url)

    print(
        "Waiting for Google OAuth callback on localhost; "
        "no credential values will be printed."
    )
    server.handle_request()
    result=dict(server.oauth_result or {})
    server.server_close()

    if not result:
        raise RuntimeError("OAuth callback timed out.")
    if result.get("error"):
        raise RuntimeError(f"Google OAuth returned: {result['error']}")
    if result.get("state") != state_value:
        raise RuntimeError("OAuth state mismatch; refusing token exchange.")
    code=str(result.get("code") or "").strip()
    if not code:
        raise RuntimeError("OAuth callback did not include an authorization code.")

    payload=exchange_code(
        client,
        code=code,
        redirect_uri=redirect_uri,
        verifier=verifier,
    )
    write_authorized_user(args.output,payload)

    print(f"Authorized-user credential written to: {args.output}")
    print("File permissions were restricted where the operating system supports it.")
    print(
        "Next: add this file's complete JSON as GitHub secret "
        "GOOGLE_OAUTH_USER_JSON, then run the Google Drive capability workflow."
    )
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(2)
