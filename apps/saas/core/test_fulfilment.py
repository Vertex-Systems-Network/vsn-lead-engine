import importlib
import os
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from lead_saas.local_fulfilment import SOURCE_CODE, verifier_settings

from .fulfilment import fulfil_outbox, run_pending
from .jobs import enqueue_job
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    DispatchOperation,
    Entitlement,
    Job,
    JobOutbox,
    UsageReservation,
    User,
)
from .result_query import results_snapshot
from .serializers import SearchSerializer
from .services import create_draft, create_workspace

COUNTER = iter(range(1, 1000))

LOCAL = {**verifier_settings("synthetic-fulfilment-test-secret"), "SAAS_LOCAL_FULFILMENT": True}


def queued_job(user, workspace, **search):
    serializer = SearchSerializer(
        data={
            "countries": ["US"],
            "categories": ["Salon"],
            "source_codes": [SOURCE_CODE],
            "result_limit": 10,
            **search,
        }
    )
    serializer.is_valid(raise_exception=True)
    job, _ = create_draft(user, workspace.id, serializer.validated_data, f"fulfil-{next(COUNTER)}")
    enqueue_job(user, workspace.id, job.id, job.revision)
    return Job.objects.get(pk=job.pk)


@override_settings(**LOCAL)
class FulfilmentTests(TestCase):
    def setUp(self):
        call_command("seed_local_source", stdout=StringIO())
        self.user = User.objects.create_user(username="fulfil-owner")
        self.workspace = create_workspace(self.user, {"name": "Fulfil", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=self.workspace,
            active=True,
            lead_limit=100,
            job_limit=5,
            provider_call_limit=5,
        )

    def test_queued_job_completes_with_accepted_results_and_settled_usage(self):
        job = queued_job(self.user, self.workspace)
        out = StringIO()
        call_command("run_jobs", stdout=out)
        self.assertIn("completed 1", out.getvalue())
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.result_count, 10)
        self.assertEqual(AcceptedResult.objects.filter(job=job).count(), 10)
        reservation = JobOutbox.objects.get(job=job).reservation
        self.assertEqual(reservation.status, "settled")
        rows = results_snapshot(self.user, self.workspace.id, job.id)
        self.assertEqual(len(rows["results"]), 10)
        for row in AcceptedResult.objects.filter(job=job):
            self.assertRegex(row.fields["phone"], r"^\+1[2-9]\d{2}[2-9]\d{6}$")
            self.assertEqual(row.country, "US")
            self.assertEqual(row.category, "Salon")

    def test_rerun_is_a_no_op(self):
        queued_job(self.user, self.workspace)
        run_pending()
        self.assertEqual(run_pending(), dict.fromkeys(run_pending(), 0))
        self.assertEqual(AcceptedResult.objects.count(), 10)

    def test_repeat_search_returns_only_new_leads_then_releases_when_exhausted(self):
        first = queued_job(self.user, self.workspace, result_limit=25)
        second = queued_job(self.user, self.workspace, result_limit=25)
        third = queued_job(self.user, self.workspace, result_limit=25)
        counts = run_pending()
        self.assertEqual(counts["completed"], 2)
        self.assertEqual(counts["empty"], 1)
        refs = [
            set(AcceptedResult.objects.filter(job=job).values_list("record_ref", flat=True))
            for job in (first, second)
        ]
        self.assertEqual(len(refs[0]), 25)
        self.assertEqual(len(refs[1]), 15)
        self.assertFalse(refs[0] & refs[1])
        tokens = AcceptedFingerprint.objects.filter(workspace=self.workspace)
        self.assertEqual(tokens.count(), len(set(tokens.values_list("token", flat=True))))
        third.refresh_from_db()
        self.assertEqual(third.status, "failed")
        self.assertEqual(JobOutbox.objects.get(job=third).reservation.status, "released")

    def test_required_website_filters_records(self):
        job = queued_job(self.user, self.workspace, required_fields=["website"])
        run_pending()
        results = AcceptedResult.objects.filter(job=job)
        self.assertEqual(results.count(), 10)
        self.assertTrue(all(row.fields.get("website") for row in results))

    def test_adapter_failure_leaves_outcome_unknown_and_reservation_held(self):
        job = queued_job(self.user, self.workspace)
        with patch("core.sources.FixtureSource.fetch", side_effect=RuntimeError("boom")):
            self.assertEqual(run_pending()["unknown"], 1)
        self.assertEqual(DispatchOperation.objects.get(job=job).status, "unknown")
        self.assertEqual(UsageReservation.objects.get(jobs=1).status, "reserved")
        self.assertFalse(AcceptedResult.objects.exists())

    def test_inactive_entitlement_is_refused_before_dispatch(self):
        job = queued_job(self.user, self.workspace)
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        self.assertEqual(run_pending()["conflict"], 1)
        self.assertFalse(DispatchOperation.objects.filter(job=job).exists())
        self.assertEqual(JobOutbox.objects.get(job=job).status, "pending")

    def test_jobs_for_sources_without_an_adapter_are_skipped(self):
        job = queued_job(self.user, self.workspace)
        with patch("core.fulfilment.adapter_for", return_value=None):
            self.assertEqual(fulfil_outbox(JobOutbox.objects.get(job=job).id), "skipped")
        self.assertEqual(JobOutbox.objects.get(job=job).status, "pending")


class ProductionGateTests(TestCase):
    def test_default_settings_refuse_to_run(self):
        self.assertEqual(settings.SAAS_LOCAL_SIGNER_KEYS, {})
        with self.assertRaises(CommandError):
            call_command("run_jobs", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("seed_local_source", stdout=StringIO())

    def test_local_fulfilment_requires_debug(self):
        import lead_saas.settings as module

        with patch.dict(
            os.environ, {"SAAS_LOCAL_FULFILMENT": "1", "SAAS_DEBUG": "0", "SAAS_SQLITE_SMOKE": "0"}
        ):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(module)
        importlib.reload(module)

    def test_local_keys_attest_only_the_fixture_source(self):
        maps = verifier_settings("synthetic-fulfilment-test-secret")
        keys = list(maps["SAAS_LOCAL_SIGNER_KEYS"].values())
        self.assertEqual(len(set(keys)), 4)
        self.assertTrue(all(len(key) == 32 for key in keys))
        for name in (
            "SAAS_RESULT_VERIFIERS",
            "SAAS_ACCEPTANCE_VERIFIERS",
            "SAAS_RECEIPT_VERIFIERS",
        ):
            self.assertEqual(set(maps[name]), {SOURCE_CODE})
        self.assertIsNone(maps["SAAS_DEDUPE_VERIFIERS"].get("other/namespace"))
