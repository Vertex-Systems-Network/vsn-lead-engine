"""Live end-to-end check: a customer job fulfilled from real Overture Places.

Disposable SQLite + dev-only local signer. Needs outbound access to the Overture
STAC catalog and public S3 release (GitHub Actions has it), plus
requirements-runtime.txt for duckdb. Run: python apps/saas/overture_smoke.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.update(
    DJANGO_SETTINGS_MODULE="lead_saas.settings",
    SAAS_DEBUG="1",
    SAAS_SQLITE_SMOKE="1",
    SAAS_LOCAL_FULFILMENT="1",
    SAAS_SECRET_KEY="disposable-overture-smoke-not-a-deployment-secret",
)


def main():
    from django.conf import settings

    with tempfile.TemporaryDirectory(prefix="vsn-overture-") as directory:
        settings.DATABASES["default"]["NAME"] = str(Path(directory) / "smoke.sqlite3")
        import django

        django.setup()
        from core.fulfilment import run_pending
        from core.jobs import enqueue_job
        from core.models import AcceptedResult, Entitlement, User
        from core.serializers import SearchSerializer
        from core.services import create_draft, create_workspace
        from django.core.management import call_command

        call_command("migrate", verbosity=0)
        call_command("seed_local_source", "--source", "overture")
        user = User.objects.create_user(username="overture-smoke")
        workspace = create_workspace(user, {"name": "Overture smoke", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=50, job_limit=5, provider_call_limit=5
        )
        search = SearchSerializer(
            data={
                "countries": ["US"],
                "categories": ["Salon"],
                "source_codes": ["overture"],
                "result_limit": 10,
            }
        )
        search.is_valid(raise_exception=True)
        job, _ = create_draft(user, workspace.id, search.validated_data, "overture-smoke-1")
        enqueue_job(user, workspace.id, job.id, job.revision)
        counts = run_pending()
        job.refresh_from_db()
        rows = list(AcceptedResult.objects.filter(job=job))
        print(f"run_pending: {counts}; job {job.status} with {job.result_count} leads")
        for row in rows[:5]:
            print(f"  {row.fields.get('business_name')} | {row.fields.get('city')}")
        if job.status != "completed" or not rows:
            raise SystemExit("FAIL: Overture job did not complete with accepted leads")
        if not all(row.fields["phone"].startswith("+1") for row in rows):
            raise SystemExit("FAIL: non-NANP phone accepted")
        print("PASS: real Overture Places job fulfilled end to end")


if __name__ == "__main__":
    main()
