from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .attempts import LEASE, MAX_ATTEMPTS, check_pre_dispatch, claim_pre_dispatch
from .jobs import RevisionConflict, cancel_pending_job, enqueue_job
from .models import Entitlement, JobAttempt, JobOutbox, Membership, SourcePolicy, UsageCounter
from .test_jobs import fixture


class PreDispatchTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.outbox = JobOutbox.objects.get(job=self.job)

    def test_fixed_lease_and_stale_token_fencing(self):
        start = timezone.now()
        with patch("core.attempts.timezone.now", return_value=start):
            first = claim_pre_dispatch(self.outbox.id)
            self.assertEqual(first.expires_at, start + LEASE)
            self.assertEqual(check_pre_dispatch(self.outbox.id, first.token).id, first.id)
            with self.assertRaises(RevisionConflict):
                claim_pre_dispatch(self.outbox.id)
        with patch("core.attempts.timezone.now", return_value=start + LEASE):
            with self.assertRaises(RevisionConflict):
                check_pre_dispatch(self.outbox.id, first.token)
            second = claim_pre_dispatch(self.outbox.id)
            self.assertNotEqual(first.token, second.token)
            self.assertEqual(second.number, 2)
            with self.assertRaises(RevisionConflict):
                check_pre_dispatch(self.outbox.id, first.token)
            with self.assertRaises(RevisionConflict):
                check_pre_dispatch(self.outbox.id, uuid4())
        first.refresh_from_db()
        self.assertEqual(first.status, "expired")
        self.assertEqual(JobAttempt.objects.filter(status="leased").count(), 1)

    def test_lease_expiring_during_preflight_is_rejected(self):
        start = timezone.now()
        with patch("core.attempts.timezone.now", return_value=start):
            lease = claim_pre_dispatch(self.outbox.id)
        with patch("core.attempts.timezone.now", side_effect=[start, start, start + LEASE]):
            with self.assertRaises(RevisionConflict):
                check_pre_dispatch(self.outbox.id, lease.token)

    def test_attempts_are_bounded_and_never_settle_or_execute(self):
        start = timezone.now()
        for index in range(MAX_ATTEMPTS):
            with patch("core.attempts.timezone.now", return_value=start + LEASE * index):
                claim_pre_dispatch(self.outbox.id)
        with patch("core.attempts.timezone.now", return_value=start + LEASE * MAX_ATTEMPTS):
            with self.assertRaises(ValidationError):
                claim_pre_dispatch(self.outbox.id)
        self.assertEqual(JobAttempt.objects.count(), MAX_ATTEMPTS)
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.result_count), ("queued", 0))
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 0)
        self.outbox.reservation.refresh_from_db()
        self.assertEqual(self.outbox.reservation.status, "reserved")
        # Explicit pre-dispatch cancellation is the safe release path, even after expiry.
        cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        self.outbox.reservation.refresh_from_db()
        self.assertEqual(self.outbox.reservation.status, "released")

    def test_membership_role_entitlement_and_cap_changes_block_check(self):
        lease = claim_pre_dispatch(self.outbox.id)
        for change in ({"active": False}, {"lead_limit": 9}, {"provider_call_limit": 1}):
            entitlement = Entitlement.objects.get(workspace=self.workspace)
            baseline = {key: getattr(entitlement, key) for key in change}
            Entitlement.objects.filter(workspace=self.workspace).update(**change)
            with self.assertRaises(PermissionDenied):
                check_pre_dispatch(self.outbox.id, lease.token)
            Entitlement.objects.filter(workspace=self.workspace).update(**baseline)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            check_pre_dispatch(self.outbox.id, lease.token)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        with self.assertRaises(Http404):
            check_pre_dispatch(self.outbox.id, lease.token)

    def test_source_kill_switch_version_and_metadata_drift_fail_closed(self):
        lease = claim_pre_dispatch(self.outbox.id)
        for change in (
            {"enabled": False},
            {"version": 2},
            {"controls": {"changed": "yes"}},
            {"max_provider_calls": 3},
            {"evidence": {}},
        ):
            policy = SourcePolicy.objects.get(pk="fixture")
            baseline = {key: getattr(policy, key) for key in change}
            SourcePolicy.objects.filter(pk=policy.pk).update(**change)
            with self.assertRaises(PermissionDenied):
                check_pre_dispatch(self.outbox.id, lease.token)
            SourcePolicy.objects.filter(pk=policy.pk).update(**baseline)

    def test_cancellation_invalidates_lease_and_changed_search_is_rejected(self):
        lease = claim_pre_dispatch(self.outbox.id)
        self.job.refresh_from_db()
        self.job.search["result_limit"] = 11
        self.job.save()
        with self.assertRaises(RevisionConflict):
            check_pre_dispatch(self.outbox.id, lease.token)
        cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        lease.refresh_from_db()
        self.assertEqual(lease.status, "cancelled")
        with self.assertRaises(RevisionConflict):
            check_pre_dispatch(self.outbox.id, lease.token)
        with self.assertRaises(RevisionConflict):
            claim_pre_dispatch(self.outbox.id)


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentAttemptTests(TransactionTestCase):
    def test_two_workers_cannot_claim_an_active_lease_together(self):
        user, workspace, job = fixture()
        enqueue_job(user, workspace.id, job.id, 0)
        outbox = JobOutbox.objects.get(job=job)
        barrier = Barrier(2)

        def claim(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    claim_pre_dispatch(outbox.id)
                    return "claimed"
                except RevisionConflict:
                    return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))
        self.assertCountEqual(results, ["claimed", "conflict"])
        self.assertEqual(JobAttempt.objects.count(), 1)
