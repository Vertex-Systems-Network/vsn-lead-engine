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
        from core.jobs import CONTROLS, EVIDENCE, enqueue_job
        from core.models import (
            Entitlement,
            Job,
            JobOutbox,
            Membership,
            SourcePolicy,
            UsageReservation,
            User,
        )
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
                settings.WEB_DASHBOARD_URL = origin + "/dashboard"
                settings.CSRF_TRUSTED_ORIGINS = [origin]

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
                    workspace=workspace,
                    active=True,
                    lead_limit=10,
                    job_limit=2,
                    provider_call_limit=4,
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
                    def __init__(self):
                        super().__init__()
                        self.token = None
                        self.hidden = {}
                        self.action = None
                        self.links = []

                    def handle_starttag(self, tag, attrs):
                        fields = dict(attrs)
                        if tag == "a" and fields.get("href"):
                            self.links.append(fields["href"])
                        if tag == "form":
                            self.action = fields.get("action")
                        if tag == "input" and fields.get("type") == "hidden" and fields.get("name"):
                            self.hidden[fields["name"]] = fields.get("value", "")
                        if tag == "input" and fields.get("name") == "csrfmiddlewaretoken":
                            self.token = fields.get("value")

                jar = CookieJar()
                opener = build_opener(HTTPCookieProcessor(jar), NoRedirect())

                def account(path, data=None, request_origin=None):
                    payload = None if data is None else urlencode(data, doseq=True).encode()
                    try:
                        response = opener.open(
                            Request(
                                backend + path,
                                data=payload,
                                headers={"Origin": request_origin} if request_origin else {},
                            ),
                            timeout=10,
                        )
                    except HTTPError as error:
                        if error.code not in {302, 303, 400, 403, 405, 409}:
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

                def native_form(path):
                    with opener.open(origin + path, timeout=10) as response:
                        body = response.read().decode()
                        assert "no-store" in response.headers.get("Cache-Control", "")
                    parser = Csrf()
                    parser.feed(body)
                    return body, parser

                missing_feedback, _ = native_form(
                    f"/dashboard/workspaces/{workspace.id}/search/new?feedback=00000000-0000-0000-0000-000000000000"
                )
                assert "saved form may have expired" in missing_feedback
                assert (
                    "Open a new draft form" in missing_feedback
                    and "return to your workspace" in missing_feedback
                )
                source_path = f"/dashboard/workspaces/{workspace.id}/sources"
                empty_catalog, _ = native_form(source_path)
                assert "No source policies are configured" in empty_catalog
                draft_path = f"/dashboard/workspaces/{workspace.id}/search/new"
                body, native = native_form(draft_path)
                assert "Create draft search" in body and "Phone (always required)" in body
                draft_action = f"/workspaces/{workspace.id}/search/new/"
                assert native.action == backend + draft_action
                assert "draft_token" in native.hidden and native.token
                payload = {
                    **native.hidden,
                    "countries": ["US", "CA"],
                    "categories": "Native bakery",
                    "source_codes": "http-fixture",
                    "result_limit": "5",
                }
                assert account(draft_action, payload, "http://localhost:3999")[0] == 403
                before = Job.objects.count()
                invalid = {
                    **payload,
                    "categories": "<script>feedback</script>",
                    "result_limit": "0",
                }
                code, _, feedback_return = account(draft_action, invalid, origin)
                assert code == 303 and "feedback=" in feedback_return["Location"]
                assert "script" not in feedback_return["Location"]
                feedback_page, retry = native_form(feedback_return["Location"].removeprefix(origin))
                assert (
                    "Check your search" in feedback_page and 'href="#result_limit"' in feedback_page
                )
                assert "&lt;script&gt;feedback&lt;/script&gt;" in feedback_page
                assert "<script>feedback</script>" not in feedback_page
                assert retry.hidden["draft_token"] == native.hidden["draft_token"]
                assert Job.objects.count() == before
                payload.update(retry.hidden)
                code, _, returned = account(draft_action, payload, origin)
                assert code == 303
                created = Job.objects.get(search__categories=["Native bakery"])
                detail_path = f"/dashboard/workspaces/{workspace.id}/jobs/{created.id}"
                assert returned["Location"] == origin + detail_path
                assert created.search["required_fields"] == ["phone"]
                assert Job.objects.count() == before + 1
                assert not UsageReservation.objects.exists() and not JobOutbox.objects.exists()
                assert account(draft_action, payload, origin)[0] == 303
                assert Job.objects.count() == before + 1
                conflict_code, _, conflict_return = account(
                    draft_action, {**payload, "result_limit": "6"}, origin
                )
                assert conflict_code == 303
                conflict_page, _ = native_form(conflict_return["Location"].removeprefix(origin))
                assert (
                    "Draft submission conflict" in conflict_page
                    and "different search" in conflict_page
                )
                Membership.objects.filter(user=user, workspace=workspace).update(role="viewer")
                denied_form, parser = native_form(draft_path)
                assert "draft_token" not in parser.hidden
                assert account(draft_action, payload, origin)[0] == 403
                Membership.objects.filter(user=user, workspace=workspace).update(role="owner")
                foreign_form, parser = native_form(f"/dashboard/workspaces/{other.id}/search/new")
                assert (
                    "Foreign private marker" not in foreign_form
                    and "draft_token" not in parser.hidden
                )
                _, stale = native_form(detail_path + "/cancel")
                cancel_action = f"/workspaces/{workspace.id}/jobs/{created.id}/cancel/"
                assert stale.action == backend + cancel_action and "confirmation" in stale.hidden
                # Synthetic catalog and internal enqueue only, never a source call.
                SourcePolicy.objects.create(
                    code="http-fixture",
                    enabled=True,
                    free_collection=True,
                    countries=["CA", "US"],
                    categories=["Native bakery"],
                    fields=["phone"],
                    evidence={k: "synthetic-only" for k in EVIDENCE},
                    controls={k: "synthetic-only" for k in CONTROLS},
                    max_provider_calls=1,
                )

                configured, _ = native_form(source_path)
                assert (
                    "http-fixture" in configured
                    and "Recorded as free; cost verification is separate" in configured
                )
                assert "synthetic-only" not in configured
                SourcePolicy.objects.create(
                    code="<script>source</script>",
                    categories=["<img src=x>"],
                    evidence={"collection": "private-secret-reference"},
                )
                escaped, _ = native_form(source_path)
                assert "&lt;script&gt;source&lt;/script&gt;" in escaped
                assert "&lt;img src=x&gt;" in escaped and "private-secret-reference" not in escaped
                Membership.objects.filter(user=user, workspace=workspace).update(role="viewer")
                viewer_catalog, _ = native_form(source_path)
                assert "http-fixture" in viewer_catalog
                Membership.objects.filter(user=user, workspace=workspace).update(role="owner")
                denied_catalog, _ = native_form(f"/dashboard/workspaces/{other.id}/sources")
                assert (
                    "http-fixture" not in denied_catalog
                    and "Foreign private marker" not in denied_catalog
                )
                enqueue_job(user, workspace.id, created.id, 0)
                assert account(cancel_action, stale.hidden, origin)[0] == 409
                assert UsageReservation.objects.get().status == "reserved"
                cancel_body, current = native_form(detail_path + "/cancel")
                assert "Current status: " in cancel_body and "queued" in cancel_body
                assert account(cancel_action, current.hidden, origin)[0] == 303
                assert account(cancel_action, current.hidden, origin)[0] == 303
                created.refresh_from_db()
                assert (created.status, created.revision) == ("cancelled", 2)
                assert UsageReservation.objects.get().status == "released"
                assert JobOutbox.objects.get().status == "cancelled"

                filtered, _ = native_form(f"/dashboard/workspaces/{workspace.id}?status=cancelled")
                assert "Native bakery" in filtered and "Synthetic bakery" not in filtered
                empty_filtered, _ = native_form(
                    f"/dashboard/workspaces/{workspace.id}?status=completed"
                )
                assert "No saved searches match this status" in empty_filtered
                paged, links = native_form(f"/dashboard/workspaces/{workspace.id}?status=draft")
                assert "Next page" in paged and "status=draft&amp;after=" in paged

                next_href = next(
                    href for href in links.links if href.startswith("?status=draft&after=")
                )
                following, links = native_form(f"/dashboard/workspaces/{workspace.id}" + next_href)
                assert "Synthetic bakery" in following and "Native bakery" not in following
                assert f"/dashboard/workspaces/{workspace.id}?status=draft" in links.links
                _, closed_form = native_form(detail_path + "/cancel")
                assert "confirmation" not in closed_form.hidden
                active_session = next(cookie.value for cookie in jar if cookie.name == "sessionid")
                form, csrf = native_form("/account/sign-out")
                assert "End your session" in form and "Keep working" in form
                assert csrf.action == backend + "/accounts/logout/"
                assert csrf.token
                assert account("/accounts/logout/")[0] == 405
                assert account("/accounts/logout/", {})[0] == 403
                code, _, returned = account(
                    "/accounts/logout/", {"csrfmiddlewaretoken": csrf.token}, origin
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
                    "PASS: Next/Django HTTP workspace, usage/window, jobs/detail, tenant denial, real CSRF login/return/logout, native draft validation/correction/replay/conflict, sign-out, role/tenant/cancel and bounded source configuration/status-filter pagination flows, old-session rejection, anonymous isolation and no-store checks (disposable SQLite)"
                )
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
