"""Disposable HTTP integration, not browser or PostgreSQL concurrency evidence."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import time as local_clock_time, timedelta
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
        from core.jobs import CONTROLS, EVIDENCE
        from core.models import (
            DailySchedule,
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
        for number in range(27):
            DailySchedule.objects.create(
                workspace=workspace,
                created_by=user,
                key=f"http-plan-{number}",
                timezone="America/Toronto",
                local_time=local_clock_time(8, 15),
                search=search.validated_data,
                request_hash="a" * 64,
                enabled=False,
            )
        DailySchedule.objects.create(
            workspace=other,
            created_by=foreign,
            key="http-foreign-private-plan",
            timezone="America/New_York",
            local_time=local_clock_time(10, 0),
            search=search.validated_data,
            request_hash="b" * 64,
            enabled=False,
        )
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
                # Public marketing pages must not require a session or expose
                # private tenant data or pretend that billing/launch is active.
                for public_path, expected in (
                    ("/", "A clearer path from business search to lead review."),
                    ("/capabilities", "Functionality with its real development status."),
                    ("/plans", "Subscriptions are not yet on sale."),
                    ("/data-handling", "Source rights and access controls before volume."),
                ):
                    public_html, _ = read(public_path, False)
                    assert expected in public_html
                    assert "Foreign private marker" not in public_html
                    assert "Synthetic &lt;workspace&gt;" not in public_html
                    assert 'href="/dashboard"' in public_html
                    assert 'name="robots"' in public_html
                    assert "noindex" in public_html
                homepage, _ = read("/", False)
                assert 'href="/account/sign-in"' in homepage
                assert "No result" in homepage and "guaranteed" in homepage
                capabilities_page, _ = read("/capabilities", False)
                assert "Implemented in development" in capabilities_page
                assert "Planned / unverified" in capabilities_page
                plans_page, _ = read("/plans", False)
                assert "no checkout" in plans_page
                assert "Price and limits: not published" in plans_page
                anonymous, _ = read("/dashboard", False)
                assert "Sign in to see your workspaces" in anonymous
                dashboard, headers = read("/dashboard")
                assert "Synthetic &lt;workspace&gt;" in dashboard
                assert "Foreign private marker" not in dashboard
                assert "no-store" in headers.get("Cache-Control", "")
                page, _ = read(f"/dashboard/workspaces/{workspace.id}")
                assert "Synthetic bakery" in page and "Next page" in page
                assert "Job status summary" in page
                assert "saved searches across all pages" in page
                assert ">27" in page
                assert 'href="?status=draft"' in page
                assert 'href="?status=completed"' in page
                assert "Active workspace:" in page
                assert (
                    f'href="/dashboard/workspaces/{workspace.id}/daily-plans"' in page
                )
                plans_page, plans_headers = read(
                    f"/dashboard/workspaces/{workspace.id}/daily-plans"
                )
                assert "Saved daily plans" in plans_page
                assert "stored daily plans across all pages" in plans_page
                assert "Disabled" in plans_page
                assert "America/Toronto" in plans_page
                assert "Private bakery marker" not in plans_page
                assert "Foreign private marker" not in plans_page
                assert "no-store" in plans_headers.get("Cache-Control", "")
                with urlopen(
                    Request(
                        backend + f"/api/v1/workspaces/{workspace.id}/daily-plans/",
                        headers={"Cookie": f"sessionid={session}"},
                    ),
                    timeout=10,
                ) as response:
                    paged = json.loads(response.read().decode())
                    assert response.status == 200
                assert paged["total"] == 27
                assert len(paged["results"]) == 25
                assert paged["next"]
                plan_id = paged["results"][0]["id"]
                plan_detail, _ = read(
                    f"/dashboard/workspaces/{workspace.id}/daily-plans/{plan_id}"
                )
                assert "Daily plan details" in plan_detail
                assert "Saved lead search preferences" in plan_detail
                assert "Synthetic bakery" in plan_detail
                assert "Disabled" in plan_detail
                assert "Foreign private marker" not in plan_detail
                assert "No activation or edit" in plan_detail
                private_detail, _ = read(
                    f"/dashboard/workspaces/{other.id}/daily-plans/{plan_id}"
                )
                assert "Synthetic bakery" not in private_detail
                assert "Foreign private marker" not in private_detail

                next_plans_page, _ = read(
                    f"/dashboard/workspaces/{workspace.id}/daily-plans?after={paged['next']}"
                )
                assert "Saved daily plans" in next_plans_page
                assert "First page" in next_plans_page
                assert "Foreign private marker" not in next_plans_page
                foreign_plans, _ = read(
                    f"/dashboard/workspaces/{other.id}/daily-plans"
                )
                assert "Foreign private marker" not in foreign_plans
                assert "Confidential" not in foreign_plans
                preview_path = f"/workspaces/{workspace.id}/schedule-preview/"
                assert backend + preview_path in page
                preview_request = Request(
                    backend + preview_path, headers={"Cookie": f"sessionid={session}"}
                )
                with urlopen(preview_request, timeout=10) as response:
                    preview_page = response.read().decode()
                    assert response.status == 200
                    assert "Next three local-day decisions" in preview_page
                    assert "does not save a schedule" in preview_page
                    assert 'value="UTC"' in preview_page
                    assert "No automatic scheduling" in preview_page
                assert "Synthetic &lt;workspace&gt;" in page
                members_page, _ = read(
                    f"/dashboard/workspaces/{workspace.id}/members"
                )
                assert "Workspace members" in members_page
                assert "Authorized workspace member roles" in members_page
                assert "Active workspace:" in members_page
                assert "Synthetic &lt;workspace&gt;" in members_page
                assert str(user.id) in members_page and "owner" in members_page
                assert "Foreign private marker" not in members_page
                foreign_members, _ = read(
                    f"/dashboard/workspaces/{other.id}/members"
                )
                assert str(foreign.id) not in foreign_members
                assert "Foreign private marker" not in foreign_members
                assert (
                    "This workspace or job is unavailable" in foreign_members
                    or "you do not have access" in foreign_members
                )
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
                plan_path = f"/workspaces/{workspace.id}/jobs/{saved[0].id}/daily-plan/"
                assert backend + plan_path in detail
                with urlopen(
                    Request(
                        backend + plan_path,
                        headers={"Cookie": f"sessionid={session}"},
                    ),
                    timeout=10,
                ) as response:
                    inactive_plan_form = response.read().decode()
                    assert response.status == 200
                    assert "Save a disabled daily plan" in inactive_plan_form
                    assert 'name="plan_token"' in inactive_plan_form
                    assert "Newly saved plans are disabled" in inactive_plan_form
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

                def native_form(path):
                    with opener.open(origin + path, timeout=10) as response:
                        body = response.read().decode()
                        assert "no-store" in response.headers.get("Cache-Control", "")
                    parser = Csrf()
                    parser.feed(body)
                    return body, parser

                unprepared, parser = native_form("/account/sign-in")
                assert "Start sign-in" in unprepared and parser.token is None
                code, _, started = account("/accounts/start-sign-in/?next=https://evil.test/")
                assert code == 303 and started["Location"] == origin + "/account/sign-in"
                form, csrf = native_form("/account/sign-in")
                assert csrf.token and csrf.action == backend + "/accounts/login/"
                assert csrf.hidden["native_login"] == "1"
                credentials = {
                    **csrf.hidden,
                    "username": user.username,
                    "password": "disposable-http-password",
                    "next": "/health/",
                }
                assert account("/accounts/login/", credentials, "http://localhost:3999")[0] == 403
                code, _, failed = account(
                    "/accounts/login/",
                    {**credentials, "password": "never-render-this-password"},
                    origin,
                )
                assert (
                    code == 303 and failed["Location"] == origin + "/account/sign-in?notice=invalid"
                )
                failed_page, _ = native_form("/account/sign-in?notice=invalid")
                assert (
                    "We could not sign you in" in failed_page
                    and "never-render-this-password" not in failed_page
                )
                from core.login_security import ACCOUNT_LIMIT, allow_login

                for _ in range(ACCOUNT_LIMIT):
                    assert allow_login("http-limited-account", "127.0.0.1")
                code, _, limited = account(
                    "/accounts/login/", {**credentials, "username": "http-limited-account"}, origin
                )
                assert (
                    code == 303
                    and limited["Location"] == origin + "/account/sign-in?notice=limited"
                )
                assert limited["Retry-After"] == "900"
                limited_page, _ = native_form("/account/sign-in?notice=limited")
                assert "Too many sign-in attempts" in limited_page
                previous_csrf = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
                code, _, returned = account("/accounts/login/?next=/health/", credentials, origin)
                assert code == 302 and returned["Location"] == origin + "/dashboard"
                assert (
                    next(cookie.value for cookie in jar if cookie.name == "csrftoken")
                    != previous_csrf
                )
                # The real login session, shared by localhost ports, must render Next.
                with opener.open(origin + "/dashboard", timeout=10) as response:
                    assert "Synthetic &lt;workspace&gt;" in response.read().decode()

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
                # Customer submit through the native Next form, not an internal call.
                submit_page, submit_form = native_form(detail_path + "/submit")
                submit_action = f"/workspaces/{workspace.id}/jobs/{created.id}/submit/"
                assert "Confirm and submit" in submit_page and "at most 25 new leads" in submit_page
                assert submit_form.action == backend + submit_action
                code, _, submitted = account(submit_action, submit_form.hidden, origin)
                assert code == 303 and submitted["Location"] == origin + detail_path
                assert Job.objects.get(pk=created.pk).status == "queued"
                queued_detail, _ = native_form(detail_path)
                assert "Queued for collection" in queued_detail
                assert "updates automatically" in queued_detail
                assert "Submit job" not in queued_detail
                code, _, resubmit = account(submit_action, submit_form.hidden, origin)
                assert code == 303 and resubmit["Location"] == origin + detail_path
                assert JobOutbox.objects.filter(job=created).count() == 1
                code, _, cancel_error = account(cancel_action, stale.hidden, origin)
                assert (
                    code == 303
                    and cancel_error["Location"] == origin + detail_path + "/cancel?notice=changed"
                )
                error_page, error_form = native_form(detail_path + "/cancel?notice=changed")
                assert "Cancellation needs review" in error_page and "queued" in error_page
                assert (
                    "Review current job" in error_page and "confirmation" not in error_form.hidden
                )
                assert error_form.action is None
                assert native_form(detail_path + "/cancel?notice=invalid")[1].token is None
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
                # Full synthetic dual-attested storage -> API -> actual Next rendering.
                # No real signer/source/registry is activated by these fixtures.
                from core.test_result_filters import MetadataAcceptanceFixture
                from core.models import AcceptedResult
                result_marker = "<img src=x onerror=synthetic-result>"
                class HttpAcceptance(MetadataAcceptanceFixture):
                    def addCleanup(self, fn):
                        self.cleanup = fn
                    def candidate_signed(self, data=None):
                        if data is None:
                            self.data["records"][0]["fields"]["business_name"] = result_marker
                        return super().candidate_signed(data)
                result_fixture = HttpAcceptance()
                try:
                    result_fixture.setUp()
                    result_fixture.accept()
                finally:
                    result_fixture.cleanup()
                Membership.objects.create(user=user, workspace=result_fixture.workspace, role="owner")
                result_path = f"/dashboard/workspaces/{result_fixture.workspace.id}/jobs/{result_fixture.job.id}/results"
                rendered, result_headers = read(result_path)
                assert "Available results" in rendered and "&lt;img src=x onerror=synthetic-result&gt;" in rendered
                assert "synthetic-record-1" not in rendered and "registry-test" not in rendered
                assert "no-store" in result_headers.get("Cache-Control", "")
                export_url = backend + result_fixture.url.replace("results/", "exports/")
                export_selection = {"result_ids": [str(r.id) for r in AcceptedResult.objects.filter(job=result_fixture.job)], "fields": ["phone", "business_name"]}
                export_csrf = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
                export_request = Request(export_url, data=json.dumps(export_selection).encode(), headers={"Content-Type": "application/json", "Idempotency-Key": "http-synthetic-export", "X-CSRFToken": export_csrf, "Origin": origin}, method="POST")
                with opener.open(export_request, timeout=10) as response:
                    exported = response.read()
                    export_receipt = response.headers["X-Export-Receipt"]
                    assert "no-store" in response.headers["Cache-Control"]
                    assert "attachment" in response.headers["Content-Disposition"]
                assert result_marker.encode() in exported and b"'+1" in exported
                with opener.open(export_request, timeout=10) as response:
                    assert response.read() == exported and response.headers["X-Export-Receipt"] == export_receipt
                Entitlement.objects.filter(workspace=result_fixture.workspace).update(export_limit=2)
                filtered_results, _ = read(result_path + "?country=CA")
                assert "1 available records excluded by filters" in filtered_results.replace("<!-- -->", "")
                assert "synthetic-result" not in filtered_results and "Second synthetic" in filtered_results
                empty_filtered, _ = read(result_path + "?country=US&category=1&source=0")
                assert "2 available records excluded by filters" in empty_filtered.replace("<!-- -->", "")
                assert "Review CSV export" not in empty_filtered and "Clear filters" in empty_filtered
                assert "synthetic-result" not in empty_filtered and "Second synthetic" not in empty_filtered
                cleared, _ = read(result_path + "?country=&category=&source=")
                assert "synthetic-result" in cleared and "Second synthetic" in cleared
                matching_results, _ = read(result_path + "?country=US&category=0&source=0")
                assert "synthetic-result" in matching_results and "/export?country=US&amp;category=0&amp;source=0" in matching_results
                preview, export_form = native_form(result_path.replace("/results", "/export") + "?country=US&category=0&source=0")
                assert "Confirm and download CSV" in preview and "one export unit" in preview
                assert "Unavailable fields" in preview and "Synthetic test source" in preview
                assert export_form.action == backend + f"/workspaces/{result_fixture.workspace.id}/jobs/{result_fixture.job.id}/export/"
                assert 'name="category"' in matching_results and 'name="source"' in matching_results
                assert "saved category:" in preview and "saved source:" in preview
                native_selection = {**export_form.hidden, "fields": ["phone"], "result_ids": [str(AcceptedResult.objects.get(job=result_fixture.job, category="software").id)]}
                assert "Choose records to include" in preview and "&lt;img src=x onerror=synthetic-result&gt;" in preview
                code, _, _ = account(f"/workspaces/{result_fixture.workspace.id}/jobs/{result_fixture.job.id}/export/", {**native_selection, "result_ids": []}, origin)
                assert code == 400
                other_row = str(AcceptedResult.objects.get(job=result_fixture.job, category="z-second").id)
                code, _, _ = account(f"/workspaces/{result_fixture.workspace.id}/jobs/{result_fixture.job.id}/export/", {**native_selection, "result_ids": [other_row]}, origin)
                assert code == 400
                export_submit_path = f"/workspaces/{result_fixture.workspace.id}/jobs/{result_fixture.job.id}/export/"
                code, native_csv, native_headers = account(export_submit_path, native_selection, origin)
                assert code == 200 and "'+1" in native_csv and "50123" in native_csv and "50124" not in native_csv and "no-store" in native_headers["Cache-Control"]
                code, repeated_csv, repeated_headers = account(export_submit_path, native_selection, origin)
                assert code == 200 and repeated_csv == native_csv and repeated_headers["X-Export-Receipt"] == native_headers["X-Export-Receipt"]
                code, conflict, _ = account(export_submit_path, {**native_selection, "fields": ["business_name"]}, origin)
                assert code == 409 and "Export needs review" in conflict
                from core.models import UsageCounter
                assert UsageCounter.objects.get(workspace=result_fixture.workspace).exports == 2
                history_path = result_path.replace("/results", "/export-receipts")
                history_html, history_headers = read(history_path)
                assert "Export preparation receipts" in history_html and "one export unit" in history_html
                assert "does not confirm a successful download" in history_html and "CSV files are not retained" in history_html
                assert export_receipt in history_html and native_headers["X-Export-Receipt"] in history_html
                assert "50123" not in history_html and "synthetic-result" not in history_html
                assert "no-store" in history_headers["Cache-Control"]
                assert history_headers["Referrer-Policy"] == "no-referrer"
                # Two genuine settled preparations, smaller readonly page for transport navigation.
                from unittest.mock import patch
                with patch("core.export_history.PAGE_SIZE", 1):
                    first_receipts, receipt_links = native_form(history_path)
                    older_href = next(href for href in receipt_links.links if href.startswith("?after="))
                    assert native_headers["X-Export-Receipt"] in first_receipts and export_receipt not in first_receipts
                    older_receipts, _ = native_form(history_path + older_href)
                    assert export_receipt in older_receipts and native_headers["X-Export-Receipt"] not in older_receipts
                    assert "Older receipts" not in older_receipts
                assert UsageCounter.objects.get(workspace=result_fixture.workspace).exports == 2
                empty_results, _ = read(f"/dashboard/workspaces/{workspace.id}/jobs/{saved[0].id}/results")
                assert "No available results" in empty_results
                Membership.objects.filter(user=user, workspace=result_fixture.workspace).update(role="viewer")
                try:
                    opener.open(export_request, timeout=10)
                    raise AssertionError("Viewer export must be denied")
                except HTTPError as exc:
                    assert exc.code == 403
                viewer_results, _ = read(result_path)
                assert "&lt;img src=x onerror=synthetic-result&gt;" in viewer_results
                assert "Review CSV export" not in viewer_results and "View export preparation receipts" not in viewer_results
                Membership.objects.filter(user=user, workspace=result_fixture.workspace).delete()
                revoked_results, _ = read(result_path)
                assert "synthetic-result" not in revoked_results
                Membership.objects.create(user=user, workspace=result_fixture.workspace, role="owner")
                SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
                withheld_results, _ = read(result_path)
                assert "recorded results are currently unavailable" in withheld_results
                assert "synthetic-result" not in withheld_results
                SourcePolicy.objects.filter(pk="fixture").update(enabled=True)
                AcceptedResult.objects.filter(job=result_fixture.job).update(delete_at=timezone.now() - timedelta(seconds=1))
                expired_results, _ = read(result_path)
                assert "No available results" in expired_results and "synthetic-result" not in expired_results
                from core.result_retention import expire_result_payloads
                from core.models import AcceptedFingerprint
                assert expire_result_payloads(user, result_fixture.workspace.id) == {"erased_count": 2, "more_due": False}
                assert all(r.fields == {} for r in AcceptedResult.objects.filter(job=result_fixture.job))
                assert AcceptedFingerprint.objects.filter(workspace=result_fixture.workspace).count() == 6
                erased_results, _ = read(result_path)
                assert "No available results" in erased_results and "synthetic-result" not in erased_results
                assert "View export preparation receipts" in erased_results
                retained_history, _ = read(history_path)
                assert export_receipt in retained_history and "50123" not in retained_history
                assert UsageCounter.objects.get(workspace=result_fixture.workspace).exports == 2
                # Self-service sign-up through the native Next form (debug default: on,
                # with a starter allowance so the new workspace can submit jobs).
                signup_page, signup_form = native_form("/account/sign-up")
                signup_action = "/accounts/sign-up/"
                assert "Create account" in signup_page and 'name="email"' in signup_page
                assert signup_form.action == backend + signup_action
                bad = {
                    **signup_form.hidden,
                    "username": "native-signup",
                    "email": "native@signup.example",
                    "password1": "x",
                }
                code, _, bad_signup = account(signup_action, {**bad, "password2": "y"}, origin)
                assert code == 303
                assert bad_signup["Location"] == origin + "/account/sign-up?notice=invalid"
                assert not User.objects.filter(username="native-signup").exists()
                secret = "native-signup-passphrase-7731"
                good = {
                    **signup_form.hidden,
                    "username": "native-signup",
                    "email": "native@signup.example",
                    "workspace_name": "Native signup workspace",
                    "password1": secret,
                    "password2": secret,
                }
                code, _, signed_up = account(signup_action, good, origin)
                assert code == 303 and signed_up["Location"] == origin + "/dashboard"
                new_workspace = Membership.objects.get(user__username="native-signup").workspace
                assert Entitlement.objects.get(workspace=new_workspace).is_current
                signed_in_dashboard, _ = native_form("/dashboard")
                assert "Native signup workspace" in signed_in_dashboard
                assert "Synthetic &lt;workspace&gt;" not in signed_in_dashboard
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
                    "PASS: Next/Django HTTP workspace, usage/window, jobs/detail, tenant denial, real CSRF login/return/logout, native login/bootstrap/failure/budget/rotation, cancellation error review, native submit/replay, native sign-up, draft validation/correction/replay/conflict, sign-out, role/tenant/cancel and bounded source configuration/status-filter pagination and dual-attested results/viewer/revocation/expiry/XSS and CSRF CSV export/replay/viewer denial, country/category/source result filters and native selected-row export preview/confirmation/empty/outside-filter denial/subset-only/conflict and readonly redacted receipt-history/no-charge/retained-after-erasure flows and payload erasure/tombstone flows, old-session rejection, anonymous isolation and no-store checks (disposable SQLite)"
                )
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
