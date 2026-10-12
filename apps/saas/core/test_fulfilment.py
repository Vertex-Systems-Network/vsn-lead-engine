import importlib
import os
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from lead_saas.local_fulfilment import LOCAL_SOURCES, SOURCE_CODE, verifier_settings

from .fulfilment import fulfil_outbox, run_pending
from .jobs import enqueue_job
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    DispatchOperation,
    Entitlement,
    Job,
    JobAttempt,
    JobOutbox,
    Membership,
    UsageReservation,
    User,
)
from .result_query import results_snapshot
from .serializers import SearchSerializer
from .services import create_draft, create_workspace
from .sources import FixtureSource

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

    def test_malformed_source_rows_are_skipped_without_poisoning_valid_leads(self):
        job = queued_job(self.user, self.workspace)
        good, other = FixtureSource().fetch(job.search, 10)[:2]
        bad_rows = [
            None,
            "not-a-record",
            {"country": "US", "source_id": "missing-fields"},
            {**good, "source_id": "bad/ref?secret"},
            {**good, "source_id": "x" * 97},
            {**good, "business_name": []},
            {**good, "business_name": "x" * 2001},
            {**good, "phone": 12345},
            {**good, "city": 42},
            {**good, "region": []},
            {**good, "website": "http://[unbalanced"},
            {**good, "website": ["invalid"]},
            {**good, "address": "second\\nline"},
        ]
        # Source payloads are untrusted. No invalid record ID, contact or
        # traceback may turn the otherwise valid batch into an unknown effect.
        with patch("core.sources.FixtureSource.fetch", return_value=bad_rows + [good, other]):
            result = run_pending(limit=1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["unknown"], 0)
        self.assertEqual(AcceptedResult.objects.filter(job=job).count(), 2)
        self.assertEqual(
            set(AcceptedResult.objects.filter(job=job).values_list("record_ref", flat=True)),
            {good["source_id"], other["source_id"]},
        )
        self.assertFalse(
            AcceptedResult.objects.filter(job=job, record_ref="bad/ref?secret").exists()
        )
        self.assertEqual(JobOutbox.objects.get(job=job).reservation.status, "settled")

    def test_source_row_without_optional_city_is_eligible_and_deduped(self):
        job = queued_job(self.user, self.workspace)
        row = FixtureSource().fetch(job.search, 10)[0].copy()
        row.pop("city", None)
        with patch("core.sources.FixtureSource.fetch", return_value=[row]):
            result = run_pending(limit=1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(AcceptedResult.objects.filter(job=job).count(), 1)
        self.assertEqual(AcceptedResult.objects.get(job=job).record_ref, row["source_id"])

    def test_source_candidate_scan_is_bounded_even_with_bad_input(self):
        job = queued_job(self.user, self.workspace)
        row = FixtureSource().fetch(job.search, 10)[0]
        with patch(
            "core.sources.FixtureSource.fetch",
            return_value=[None] * 100 + [row],
        ):
            result = run_pending(limit=1)
        self.assertEqual(result["empty"], 1)
        self.assertEqual(result["unknown"], 0)
        self.assertFalse(AcceptedResult.objects.filter(job=job).exists())
        self.assertEqual(JobOutbox.objects.get(job=job).reservation.status, "released")

    def test_required_website_filters_records(self):
        job = queued_job(self.user, self.workspace, required_fields=["website"])
        run_pending()
        results = AcceptedResult.objects.filter(job=job)
        self.assertEqual(results.count(), 10)
        self.assertTrue(all(row.fields.get("website") for row in results))

    def test_adapter_failure_leaves_outcome_unknown_and_reservation_held(self):
        job = queued_job(self.user, self.workspace)
        injected = "api-token=should-never-appear-in-logs"
        with (
            patch("core.sources.FixtureSource.fetch", side_effect=RuntimeError(injected)),
            self.assertLogs("core.fulfilment", level="WARNING") as captured,
        ):
            self.assertEqual(run_pending()["unknown"], 1)
        self.assertNotIn(injected, " ".join(captured.output))
        self.assertEqual(DispatchOperation.objects.get(job=job).status, "unknown")
        self.assertEqual(UsageReservation.objects.get(jobs=1).status, "reserved")
        self.assertFalse(AcceptedResult.objects.exists())

    def test_preflight_exceptions_do_not_echo_adapter_secrets_or_identifiers(self):
        job = queued_job(self.user, self.workspace)
        injected = "authorization-header=private-test-marker"
        with (
            patch("core.fulfilment.claim_pre_dispatch", side_effect=RuntimeError(injected)),
            self.assertLogs("core.fulfilment", level="WARNING") as captured,
        ):
            self.assertEqual(run_pending(limit=1)["conflict"], 1)
        logs = " ".join(captured.output)
        self.assertNotIn(injected, logs)
        self.assertNotIn(str(job.pk), logs)
        self.assertEqual(JobOutbox.objects.get(job=job).status, "pending")
        self.assertFalse(DispatchOperation.objects.filter(job=job).exists())

    def test_inactive_owner_falls_back_to_active_authorized_admin(self):
        administrator = User.objects.create_user(username="fulfil-active-admin")
        Membership.objects.create(workspace=self.workspace, user=administrator, role="admin")
        job = queued_job(administrator, self.workspace)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        result = run_pending(limit=1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["conflict"], 0)
        job.refresh_from_db()
        self.assertEqual((job.status, job.result_count), ("completed", 10))
        self.assertEqual(JobOutbox.objects.get(job=job).reservation.status, "settled")
        self.assertEqual(AcceptedResult.objects.filter(job=job).count(), 10)

    def test_no_active_privileged_member_fails_closed_before_dispatch(self):
        viewer = User.objects.create_user(username="fulfil-active-viewer")
        Membership.objects.create(workspace=self.workspace, user=viewer, role="viewer")
        job = queued_job(self.user, self.workspace)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        with self.assertLogs("core.fulfilment", level="WARNING") as logged:
            result = run_pending(limit=1)
        self.assertEqual(result["conflict"], 1)
        self.assertNotIn(str(job.pk), " ".join(logged.output))
        self.assertFalse(DispatchOperation.objects.filter(job=job).exists())
        self.assertFalse(JobAttempt.objects.filter(outbox__job=job).exists())
        self.assertEqual(JobOutbox.objects.get(job=job).reservation.status, "reserved")
        job.refresh_from_db()
        self.assertEqual(job.status, "queued")

    def test_inactive_entitlement_is_refused_before_dispatch(self):
        job = queued_job(self.user, self.workspace)
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        self.assertEqual(run_pending()["conflict"], 1)
        self.assertFalse(DispatchOperation.objects.filter(job=job).exists())
        self.assertEqual(JobOutbox.objects.get(job=job).status, "pending")

    def test_expired_and_retained_possible_effect_rows_do_not_starve_fulfilment(self):
        expired = queued_job(self.user, self.workspace)
        uncertain = queued_job(self.user, self.workspace)
        eligible = queued_job(self.user, self.workspace)
        expired_outbox = JobOutbox.objects.get(job=expired)
        uncertain_outbox = JobOutbox.objects.get(job=uncertain)
        JobOutbox.objects.filter(pk=expired_outbox.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        attempt = JobAttempt.objects.create(
            outbox=uncertain_outbox,
            number=1,
            job_revision=uncertain.revision,
            status="started",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        operation = DispatchOperation.objects.create(
            workspace=self.workspace,
            job=uncertain,
            outbox=uncertain_outbox,
            attempt=attempt,
            source_code=SOURCE_CODE,
            request_hash=uncertain.request_hash,
            policy_version=1,
            policy_fingerprint="a" * 64,
            call_limit=1,
            status="unknown",
            unknown_at=timezone.now(),
        )

        result = run_pending(limit=1)
        self.assertEqual(
            result, {"completed": 1, "empty": 0, "unknown": 0, "skipped": 0, "conflict": 0}
        )
        eligible.refresh_from_db()
        expired.refresh_from_db()
        uncertain.refresh_from_db()
        expired_outbox.refresh_from_db()
        uncertain_outbox.refresh_from_db()
        self.assertEqual(eligible.status, "completed")
        self.assertEqual(expired.status, "queued")
        self.assertEqual(uncertain.status, "queued")
        self.assertEqual(expired_outbox.status, "pending")
        self.assertEqual(uncertain_outbox.status, "pending")
        self.assertTrue(DispatchOperation.objects.filter(pk=operation.pk).exists())
        self.assertEqual(expired_outbox.reservation.status, "reserved")
        self.assertEqual(uncertain_outbox.reservation.status, "reserved")
        self.assertEqual(AcceptedResult.objects.filter(job=eligible).count(), 10)

    def test_live_leases_and_exhausted_attempts_do_not_starve_safe_job(self):
        leased = queued_job(self.user, self.workspace)
        exhausted = queued_job(self.user, self.workspace)
        eligible = queued_job(self.user, self.workspace)
        now = timezone.now()
        leased_outbox = JobOutbox.objects.get(job=leased)
        exhausted_outbox = JobOutbox.objects.get(job=exhausted)
        lease = JobAttempt.objects.create(
            outbox=leased_outbox,
            number=1,
            job_revision=leased.revision,
            status="leased",
            expires_at=now + timedelta(seconds=45),
        )
        for number in (1, 2, 3):
            JobAttempt.objects.create(
                outbox=exhausted_outbox,
                number=number,
                job_revision=exhausted.revision,
                status="expired",
                expires_at=now - timedelta(seconds=number),
            )

        result = run_pending(limit=1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["conflict"], 0)
        eligible.refresh_from_db()
        self.assertEqual(eligible.status, "completed")
        self.assertEqual(JobAttempt.objects.filter(outbox=leased_outbox).count(), 1)
        self.assertEqual(JobAttempt.objects.filter(outbox=exhausted_outbox).count(), 3)
        self.assertEqual(leased_outbox.reservation.status, "reserved")
        self.assertEqual(exhausted_outbox.reservation.status, "reserved")
        lease.refresh_from_db()
        self.assertEqual(lease.status, "leased")

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

    def test_local_keys_attest_only_the_dev_sources(self):
        maps = verifier_settings("synthetic-fulfilment-test-secret")
        keys = list(maps["SAAS_LOCAL_SIGNER_KEYS"].values())
        self.assertEqual(len(set(keys)), 4)
        self.assertTrue(all(len(key) == 32 for key in keys))
        for name in (
            "SAAS_RESULT_VERIFIERS",
            "SAAS_ACCEPTANCE_VERIFIERS",
            "SAAS_RECEIPT_VERIFIERS",
        ):
            self.assertEqual(set(maps[name]), set(LOCAL_SOURCES))
        self.assertIsNone(maps["SAAS_DEDUPE_VERIFIERS"].get("other/namespace"))
