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
from pathlib import Path
from urllib.request import Request, urlopen
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
        user = User.objects.create_user(username="synthetic-next-owner")
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
                print(
                    "PASS: Next/Django HTTP workspace, usage/window, jobs/detail, tenant denial, anonymous isolation and no-store checks (disposable SQLite)"
                )
            finally:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
