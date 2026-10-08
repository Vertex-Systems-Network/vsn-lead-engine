from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .attempts import check_pre_dispatch, claim_pre_dispatch
from .dispatch import begin_dispatch
from .export_forms import export_context
from .jobs import cancel_pending_job, enqueue_job
from .models import DailySchedule, Entitlement, JobOutbox, ScheduleOccurrence, UsageCounter
from .periods import advance_period
from .result_query import results_snapshot
from .schedules import create_daily_schedule, materialize_daily
from .test_jobs import fixture
from .test_result_exports import ExportFixture
from .usage import reserve_usage
from .usage_snapshot import usage_snapshot


class EntitlementExpiryTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()

    def expire(self):
        Entitlement.objects.filter(workspace=self.workspace).update(valid_until=timezone.now())

    def test_deadline_blocks_new_reservation_enqueue_and_existing_enqueue_replay(self):
        self.expire()
        with self.assertRaises(PermissionDenied):
            reserve_usage(self.user, self.workspace.id, "new", {"leads": 1})
        with self.assertRaises(PermissionDenied):
            enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageCounter.objects.exists())
        Entitlement.objects.filter(workspace=self.workspace).update(valid_until=None)
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.expire()
        with self.assertRaises(PermissionDenied):
            enqueue_job(self.user, self.workspace.id, self.job.id, 0)

    def test_expiry_after_claim_blocks_check_and_start_but_keeps_safe_cancellation(self):
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        outbox = JobOutbox.objects.get(job=self.job)
        lease = claim_pre_dispatch(outbox.id)
        self.expire()
        with self.assertRaises(PermissionDenied):
            check_pre_dispatch(outbox.id, lease.token)
        with self.assertRaises(PermissionDenied):
            begin_dispatch(outbox.id, lease.token)
        outbox.reservation.refresh_from_db()
        self.assertEqual(outbox.reservation.status, "reserved")
        cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        outbox.reservation.refresh_from_db()
        self.assertEqual(outbox.reservation.status, "released")

    def test_expiry_before_claim_does_not_create_a_lease(self):
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        outbox = JobOutbox.objects.get(job=self.job)
        self.expire()
        with self.assertRaises(PermissionDenied):
            claim_pre_dispatch(outbox.id)
        self.assertFalse(outbox.attempts.exists())

    def test_deadline_blocks_period_advance_without_resetting_counters(self):
        self.expire()
        now = timezone.now()
        with self.assertRaises(PermissionDenied):
            advance_period(
                self.user,
                self.workspace.id,
                now - timedelta(hours=1),
                now + timedelta(days=1),
                "window",
            )
        self.assertFalse(UsageCounter.objects.exists())
        self.assertFalse(usage_snapshot(self.user, self.workspace.id)["entitlement_active"])

    def test_daily_materialization_rechecks_deadline_without_creating_occurrence(self):
        schedule, _ = create_daily_schedule(
            self.user, self.workspace.id, self.job.search, "UTC", time(0), "daily"
        )
        DailySchedule.objects.filter(pk=schedule.id).update(enabled=True)
        self.expire()
        with self.assertRaises(PermissionDenied):
            materialize_daily(self.user, self.workspace.id, schedule.id, timezone.now().date(), 1)
        self.assertFalse(ScheduleOccurrence.objects.exists())


class ExportExpiryTests(ExportFixture, TestCase):
    def test_expired_grant_withholds_payload_and_blocks_preview_new_export_and_replay(self):
        receipt = self.export()
        Entitlement.objects.filter(workspace=self.workspace).update(valid_until=timezone.now())
        for callback in [
            lambda: self.export(),
            lambda: self.export(key="new"),
            lambda: export_context(self.user, self.workspace.id, self.job.id),
        ]:
            with self.assertRaises(PermissionDenied):
                callback()
        snapshot = results_snapshot(self.user, self.workspace.id, self.job.id)
        self.assertEqual(snapshot["results"], [])
        self.assertFalse(snapshot["can_review_export"])
        self.assertEqual(snapshot["withheld_count"], 1)
        self.assertTrue(receipt.created)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)


class PastEffectExpiryTests(TestCase):
    def test_verified_past_provider_effect_still_settles_after_entitlement_expiry(self):
        from django.test import override_settings

        from .receipts import reconcile_receipt
        from .test_receipts import VERIFIERS, proof, started

        user, workspace, job, outbox, operation = started()
        Entitlement.objects.filter(workspace=workspace).update(valid_until=timezone.now())
        with override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS):
            reconcile_receipt(user, workspace.id, operation.id, *proof(operation))
        outbox.reservation.refresh_from_db()
        self.assertEqual(outbox.reservation.status, "settled")
        self.assertEqual(UsageCounter.objects.get(workspace=workspace).provider_calls, 1)
