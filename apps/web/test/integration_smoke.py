"""Disposable HTTP integration, not browser or PostgreSQL concurrency evidence."""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import timedelta
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener, urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "saas"))
os.environ.update(
    DJANGO_SETTINGS_MODULE="lead_saas.settings",
    SAAS_DEBUG="1",
    SAAS_SQLITE_SMOKE="1",
    SAAS_SECRET_KEY="disposable-http-smoke-not-a-deployment-secret",
)


def main():
    from django.conf import settings

    with tempfile.TemporaryDirectory(prefix="vsn-next-http-") as directory:
        settings.DATABASES["default"]["NAME"] = str(Path(directory) / "smoke.sqlite3")
        import django

        django.setup()
        from core.models import Entitlement, User
        from core.periods import advance_period
        from core.serializers import SearchSerializer
        from core.services import create_draft, create_workspace
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.test import Client
        from django.utils import timezone

        call_command("migrate", verbosity=0)
        user = User.objects.create_user(
            username="synthetic-next-owner", password="disposable-http-password"
        )
        foreign = User.objects.create_user(username="synthetic-next-other")
        workspace = create_workspace(user, {"name": "Synthetic <workspace>", "timezone": "UTC"})
        other = create_workspace(foreign, {"name": "Foreign private marker", "timezone": "UTC"})
        search = SearchSerializer(
            data={"countries": ["US", "CA"], "categories": ["Synthetic bakery"]}
        )
        search.is_valid(raise_exception=True)
        saved = [
            create_draft(user, workspace.id, search.validated_data, f"http-smoke-{i}")[0]
            for i in range(27)
        ]
        client = Client()
        client.force_login(user)
        session = client.cookies["sessionid"].value

        class Quiet(WSGIRequestHandler):
            def log_message(self, format, *args):
                pass

        server = make_server("localhost", 0, get_wsgi_application(), handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with socket.socket() as sock:
            sock.bind(("localhost", 0))
            port = sock.getsockname()[1]
        backend = f"http://localhost:{server.server_port}"
        env = {
            **os.environ,
            "SAAS_BACKEND_ORIGIN": backend,
            "SAAS_PUBLIC_ORIGIN": backend,
            "NEXT_TELEMETRY_DISABLED": "1",
        }
        with (Path(directory) / "next.log").open("w") as log:
            process = subprocess.Popen(
                ["npm", "run", "start", "--", "--port", str(port)],
                cwd=ROOT / "web",
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                origin = f"http://localhost:{port}"
                # Fixed trusted configuration, not a browser-provided next host.
                settings.LOGIN_REDIRECT_URL = origin + "/dashboard"
                settings.LOGOUT_REDIRECT_URL = origin + "/dashboard"

                def read(path, authenticated=True):
                    headers = {"Cookie": f"sessionid={session}"} if authenticated else {}
                    with urlopen(Request(origin + path, headers=headers), timeout=10) as response:
                        return response.read().decode(), response.headers

                for _ in range(50):
                    if process.poll() is not None:
                        raise RuntimeError("Next server failed to start")
                    try:
                        read("/dashboard", False)
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Next startup timeout")
                anonymous, _ = read("/dashboard", False)
                assert "Sign in to see your workspaces" in anonymous
                dashboard, headers = read("/dashboard")
                assert "Synthetic &lt;workspace&gt;" in dashboard
                assert "Foreign private marker" not in dashboard
                assert "no-store" in headers.get("Cache-Control", "")
                page, _ = read(f"/dashboard/workspaces/{workspace.id}")
                assert "Synthetic bakery" in page and "Next page" in page
                assert (
                    "Cumulative development counters" in page
                    and "Settled and reserved usage" in page
                )
                Entitlement.objects.create(
                    workspace=workspace, active=True, lead_limit=10, job_limit=2
                )
                now = timezone.now()
                advance_period(
                    user,
                    workspace.id,
                    now - timedelta(seconds=1),
                    now + timedelta(minutes=5),
                    "http-period",
                )
                period_page, _ = read(f"/dashboard/workspaces/{workspace.id}")
                assert "Internal accounting window" in period_page
                assert "Rollover waits for unresolved reservations" in period_page
                detail, _ = read(f"/dashboard/workspaces/{workspace.id}/jobs/{saved[0].id}")
                assert "Saved search" in detail and "Review cancellation" in detail
                denied, _ = read(f"/dashboard/workspaces/{other.id}")
                assert "Foreign private marker" not in denied
                assert (
                    "This workspace or job is unavailable" in denied
                    or "you do not have access" in denied
                )
                again, _ = read("/dashboard", False)
                assert "Synthetic &lt;workspace&gt;" not in again

                class NoRedirect(HTTPRedirectHandler):
                    def redirect_request(self, request, fp, code, msg, headers, newurl):
                        return None

                class Csrf(HTMLParser):
                    token = None

                    def handle_starttag(self, tag, attrs):
                        fields = dict(attrs)
                        if tag == "input" and fields.get("name") == "csrfmiddlewaretoken":
                            self.token = fields.get("value")

                jar = CookieJar()
                opener = build_opener(HTTPCookieProcessor(jar), NoRedirect())

                def account(path, data=None):
                    payload = None if data is None else urlencode(data).encode()
                    try:
                        response = opener.open(Request(backend + path, data=payload), timeout=10)
                    except HTTPError as error:
                        if error.code not in {302, 303, 403, 405}:
                            raise
                        response = error
                    with response:
                        return response.code, response.read().decode(), response.headers

                _, form, _ = account("/accounts/login/")
                csrf = Csrf()
                csrf.feed(form)
                assert csrf.token
                code, _, returned = account(
                    "/accounts/login/",
                    {
                        "username": user.username,
                        "password": "disposable-http-password",
                        "csrfmiddlewaretoken": csrf.token,
                        "next": "https://evil.example.test/",
                    },
                )
                assert code == 302 and returned["Location"] == origin + "/dashboard"
                # The real login session, shared by localhost ports, must render Next.
                with opener.open(origin + "/dashboard", timeout=10) as response:
                    assert "Synthetic &lt;workspace&gt;" in response.read().decode()
                active_session = next(cookie.value for cookie in jar if cookie.name == "sessionid")
                code, form, _ = account("/accounts/sign-out/")
                assert code == 200 and "End your session" in form
                csrf = Csrf()
                csrf.feed(form)
                assert csrf.token
                assert account("/accounts/logout/")[0] == 405
                assert account("/accounts/logout/", {})[0] == 403
                code, _, returned = account(
                    "/accounts/logout/", {"csrfmiddlewaretoken": csrf.token}
                )
                assert code == 302 and returned["Location"] == origin + "/dashboard"
                with opener.open(origin + "/dashboard", timeout=10) as response:
                    logged_out = response.read().decode()
                    assert "Sign in to see your workspaces" in logged_out
                    assert "Synthetic &lt;workspace&gt;" not in logged_out
                # Even replaying the old HTTP-only session cannot restore access.
                with urlopen(
                    Request(
                        origin + "/dashboard", headers={"Cookie": f"sessionid={active_session}"}
                    ),
                    timeout=10,
                ) as response:
                    assert "Synthetic &lt;workspace&gt;" not in response.read().decode()
                print(
                    "PASS: Next/Django HTTP workspace, usage/window, jobs/detail, tenant denial, real CSRF login/return/logout, old-session rejection, anonymous isolation and no-store checks (disposable SQLite)"
                )
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
