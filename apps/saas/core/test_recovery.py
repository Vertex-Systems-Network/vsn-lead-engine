from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .attempts import check_pre_dispatch, claim_pre_dispatch
from .jobs import RevisionConflict, enqueue_job
from .models import JobAttempt, JobOutbox, Membership, UsageCounter
from .recovery import expire_one, expire_pending_intents
from .services import create_draft
from .test_jobs import fixture
from .usage import settle_usage


class RecoveryTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.intent = JobOutbox.objects.get(job=self.job)

    def overdue(self):
        now = timezone.now()
        JobOutbox.objects.filter(pk=self.intent.id).update(expires_at=now)
        return now

    def test_expiry_releases_unused_capacity_and_invalidates_lease_once(self):
        lease = claim_pre_dispatch(self.intent.id)
        self.overdue()
        # Cleanup must work even when the originally authorized actor has been revoked.
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(expire_pending_intents(), {"examined": 1, "expired": 1})
        self.assertEqual(expire_pending_intents(), {"examined": 0, "expired": 0})
        self.assertFalse(expire_one(self.intent.id))
        self.job.refresh_from_db()
        self.intent.refresh_from_db()
        lease.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("cancelled", 2))
        self.assertEqual(self.intent.status, "cancelled")
        self.assertEqual(lease.status, "cancelled")
        self.assertEqual(self.intent.reservation.status, "released")
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 0)
        with self.assertRaises(RevisionConflict):
            check_pre_dispatch(self.intent.id, lease.token)

    def test_future_and_legacy_null_deadlines_are_not_inferred_expired(self):
        self.assertEqual(expire_pending_intents()["expired"], 0)
        JobOutbox.objects.filter(pk=self.intent.id).update(expires_at=None)
        self.assertFalse(expire_one(self.intent.id))
        self.assertEqual(expire_pending_intents()["examined"], 0)

    def test_running_or_settled_work_is_never_refunded(self):
        self.overdue()
        self.job.refresh_from_db()
        self.job.status = "running"
        self.job.save(update_fields=["status"])
        self.assertFalse(expire_one(self.intent.id))
        self.assertEqual(expire_pending_intents()["expired"], 0)
        self.job.status = "queued"
        self.job.save(update_fields=["status"])
        settle_usage(
            self.user,
            self.workspace.id,
            self.intent.reservation_id,
            {"jobs": 1, "provider_calls": 1},
        )
        self.assertFalse(expire_one(self.intent.id))
        self.assertEqual(expire_pending_intents()["expired"], 0)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 1)

    def test_batch_bound_and_operator_command(self):
        self.overdue()
        second, _ = create_draft(self.user, self.workspace.id, self.job.search, "second")
        enqueue_job(self.user, self.workspace.id, second.id, 0)
        JobOutbox.objects.filter(job=second).update(expires_at=timezone.now())
        for invalid in (0, 101, True, 1.5):
            with self.assertRaises(ValidationError):
                expire_pending_intents(limit=invalid)
        self.assertEqual(expire_pending_intents(limit=1), {"examined": 1, "expired": 1})
        output = StringIO()
        call_command("expire_pending_intents", limit=1, stdout=output)
        self.assertIn("Examined 1; expired 1.", output.getvalue())
        self.assertEqual(JobOutbox.objects.filter(status="cancelled").count(), 2)

    def test_deadline_blocks_claim_and_limits_lease_duration(self):
        start = timezone.now()
        end = start + timedelta(seconds=10)
        JobOutbox.objects.filter(pk=self.intent.id).update(expires_at=end)
        with patch("core.attempts.timezone.now", return_value=start):
            lease = claim_pre_dispatch(self.intent.id)
            self.assertEqual(lease.expires_at, end)
        with patch("core.attempts.timezone.now", return_value=end):
            with self.assertRaises(RevisionConflict):
                check_pre_dispatch(self.intent.id, lease.token)
            with self.assertRaises(RevisionConflict):
                claim_pre_dispatch(self.intent.id)

    def test_failed_job_update_rolls_back_release_and_intent(self):
        self.overdue()
        with patch("core.recovery.Job.save", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                expire_one(self.intent.id)
        self.intent.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.status, "pending")
        self.assertEqual(self.intent.reservation.status, "reserved")


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentRecoveryTests(TransactionTestCase):
    def test_duplicate_cleanup_releases_one_intent(self):
        user, workspace, job = fixture()
        enqueue_job(user, workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        JobOutbox.objects.filter(pk=intent.id).update(expires_at=timezone.now())
        barrier = Barrier(2)

        def expire(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return expire_one(intent.id)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(expire, range(2)))
        self.assertCountEqual(results, [True, False])
        job.refresh_from_db()
        self.assertEqual(job.revision, 2)
        self.assertFalse(JobAttempt.objects.exists())
