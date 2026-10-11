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
from .jobs import RevisionConflict, cancel_pending_job, enqueue_job
from .models import (
    DispatchOperation,
    Entitlement,
    Job,
    JobAttempt,
    JobOutbox,
    Membership,
    UsageCounter,
)
from .recovery import expire_one, expire_pending_intents
from .services import create_draft
from .test_jobs import fixture


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
        # Simulate retained legacy settled state; normal job settlement now
        # requires verified reconciliation rather than the generic usage service.
        self.intent.reservation.status = "settled"
        self.intent.reservation.settlement = {
            "leads": 0,
            "jobs": 1,
            "provider_calls": 1,
            "exports": 0,
        }
        self.intent.reservation.save()
        UsageCounter.objects.filter(workspace=self.workspace).update(jobs=1, provider_calls=1)
        self.assertFalse(expire_one(self.intent.id))
        self.assertEqual(expire_pending_intents()["expired"], 0)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 1)

    def test_mismatched_write_ahead_dispatch_evidence_blocks_all_release_paths(self):
        """A retained possible-effect record overrides stale pending flags."""
        lease = claim_pre_dispatch(self.intent.id)
        operation = DispatchOperation.objects.create(
            workspace=self.workspace,
            job=self.job,
            outbox=self.intent,
            attempt=lease,
            source_code="fixture",
            request_hash=self.job.request_hash,
            policy_version=1,
            policy_fingerprint="a" * 64,
            call_limit=1,
            status="unknown",
            unknown_at=timezone.now(),
        )
        self.overdue()
        self.assertFalse(expire_one(self.intent.id))
        self.assertEqual(expire_pending_intents(), {"examined": 0, "expired": 0})
        with self.assertRaises(RevisionConflict):
            cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        self.intent.refresh_from_db()
        self.job.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        lease.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("queued", 1))
        self.assertEqual(self.intent.status, "pending")
        self.assertEqual(self.intent.reservation.status, "reserved")
        self.assertEqual(lease.status, "leased")
        self.assertTrue(DispatchOperation.objects.filter(pk=operation.id).exists())

    def test_started_attempt_without_operation_blocks_release_after_restore(self):
        """A started lease without its ledger cannot justify a refund."""
        lease = claim_pre_dispatch(self.intent.id)
        JobAttempt.objects.filter(pk=lease.id).update(status="started")
        self.overdue()
        self.assertFalse(expire_one(self.intent.id))
        with self.assertRaises(RevisionConflict):
            cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        self.assertEqual(expire_pending_intents(), {"examined": 0, "expired": 0})
        self.intent.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual((self.intent.status, self.job.status), ("pending", "queued"))
        self.assertEqual(self.intent.reservation.status, "reserved")
        self.assertEqual(JobAttempt.objects.get(pk=lease.pk).status, "started")
        self.assertFalse(DispatchOperation.objects.exists())

    def test_blocked_possible_effect_rows_cannot_starve_safe_expiry_batches(self):
        """Two older unsafe rows must not hide a later eligible row at limit=1."""
        # The shared two-job fixture limit is too small for this three-job
        # synthetic queue; enlarge only this disposable test entitlement.
        Entitlement.objects.filter(workspace=self.workspace).update(
            lead_limit=40, job_limit=3, provider_call_limit=6
        )
        now = timezone.now()
        first_attempt = JobAttempt.objects.create(
            outbox=self.intent,
            number=1,
            job_revision=1,
            status="started",
            expires_at=now - timedelta(days=3),
        )
        DispatchOperation.objects.create(
            workspace=self.workspace,
            job=self.job,
            outbox=self.intent,
            attempt=first_attempt,
            source_code="fixture",
            request_hash=self.job.request_hash,
            policy_version=1,
            policy_fingerprint="a" * 64,
            call_limit=1,
            status="unknown",
            unknown_at=now - timedelta(days=3),
        )
        JobOutbox.objects.filter(pk=self.intent.pk).update(expires_at=now - timedelta(days=3))
        blocked_job, _ = create_draft(
            self.user, self.workspace.id, self.job.search, "blocked-started"
        )
        enqueue_job(self.user, self.workspace.id, blocked_job.pk, 0)
        blocked_outbox = JobOutbox.objects.get(job=blocked_job)
        blocked_attempt = JobAttempt.objects.create(
            outbox=blocked_outbox,
            number=1,
            job_revision=1,
            status="done",
            expires_at=now - timedelta(days=2),
        )
        JobOutbox.objects.filter(pk=blocked_outbox.pk).update(expires_at=now - timedelta(days=2))
        safe_job, _ = create_draft(self.user, self.workspace.id, self.job.search, "releasable")
        enqueue_job(self.user, self.workspace.id, safe_job.pk, 0)
        safe_outbox = JobOutbox.objects.get(job=safe_job)
        safe_lease = JobAttempt.objects.create(
            outbox=safe_outbox,
            number=1,
            job_revision=1,
            status="leased",
            expires_at=now - timedelta(days=1),
        )
        JobOutbox.objects.filter(pk=safe_outbox.pk).update(expires_at=now - timedelta(days=1))

        self.assertEqual(expire_pending_intents(limit=1), {"examined": 1, "expired": 1})
        self.assertEqual(expire_pending_intents(limit=1), {"examined": 0, "expired": 0})
        call_output = StringIO()
        call_command("expire_pending_intents", limit=1, stdout=call_output)
        self.assertIn("Examined 0; expired 0.", call_output.getvalue())
        self.intent.refresh_from_db()
        blocked_outbox.refresh_from_db()
        safe_outbox.refresh_from_db()
        safe_job.refresh_from_db()
        safe_lease.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        blocked_outbox.reservation.refresh_from_db()
        safe_outbox.reservation.refresh_from_db()
        blocked_attempt.refresh_from_db()
        self.assertEqual(self.intent.status, "pending")
        self.assertEqual(blocked_outbox.status, "pending")
        self.assertEqual(self.intent.reservation.status, "reserved")
        self.assertEqual(blocked_outbox.reservation.status, "reserved")
        self.assertEqual(blocked_attempt.status, "done")
        self.assertEqual(safe_outbox.status, "cancelled")
        self.assertEqual(safe_job.status, "cancelled")
        self.assertEqual(safe_outbox.reservation.status, "released")
        self.assertEqual(safe_lease.status, "cancelled")
        self.assertEqual(DispatchOperation.objects.count(), 1)

    def test_unreleasable_revision_does_not_starve_later_expired_intents(self):
        self.overdue()
        Job.objects.filter(pk=self.job.pk).update(revision=2147483647)
        second, _ = create_draft(self.user, self.workspace.id, self.job.search, "eligible")
        enqueue_job(self.user, self.workspace.id, second.pk, 0)
        JobOutbox.objects.filter(job=second).update(expires_at=timezone.now())
        self.assertEqual(expire_pending_intents(limit=1), {"examined": 1, "expired": 1})
        self.assertEqual(expire_pending_intents(limit=1), {"examined": 0, "expired": 0})
        self.intent.refresh_from_db()
        self.job.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual((self.intent.status, self.job.revision), ("pending", 2147483647))
        self.assertEqual(self.intent.reservation.status, "reserved")

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
