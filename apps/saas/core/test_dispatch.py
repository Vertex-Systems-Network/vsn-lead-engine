import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .attempts import check_pre_dispatch, claim_pre_dispatch
from .dispatch import begin_dispatch, dispatch_snapshot, mark_outcome_unknown
from .jobs import RevisionConflict, cancel_pending_job, enqueue_job
from .models import DispatchOperation, JobAttempt, JobOutbox, Membership, User
from .recovery import expire_one
from .services import create_workspace
from .test_jobs import fixture


class DispatchLedgerTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.outbox = JobOutbox.objects.get(job=self.job)
        self.attempt = claim_pre_dispatch(self.outbox.id)

    def test_start_commits_identity_and_preserves_uncertain_capacity(self):
        operation = begin_dispatch(self.outbox.id, self.attempt.token)[0]
        self.job.refresh_from_db()
        self.outbox.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("running", 2))
        self.assertEqual(self.outbox.status, "started")
        self.assertEqual(self.attempt.status, "started")
        self.assertNotEqual(operation.provider_key, self.attempt.token)
        self.assertEqual(operation.request_hash, self.job.request_hash)
        self.assertEqual(
            operation.policy_fingerprint, self.outbox.source_snapshot["fixture"]["hash"]
        )
        self.assertEqual(operation.workspace_id, self.workspace.id)
        with self.assertRaises(RevisionConflict):
            begin_dispatch(self.outbox.id, self.attempt.token)
        with self.assertRaises(RevisionConflict):
            check_pre_dispatch(self.outbox.id, self.attempt.token)
        with self.assertRaises(RevisionConflict):
            cancel_pending_job(self.user, self.workspace.id, self.job.id, 2)
        JobOutbox.objects.filter(pk=self.outbox.id).update(expires_at=timezone.now())
        self.assertFalse(expire_one(self.outbox.id))
        self.outbox.reservation.refresh_from_db()
        self.assertEqual(self.outbox.reservation.status, "reserved")
        self.assertEqual(
            dispatch_snapshot(self.user, self.workspace.id, self.outbox.id)[0].provider_key,
            operation.provider_key,
        )
        self.assertEqual(DispatchOperation.objects.count(), 1)

    def test_unknown_is_idempotent_does_not_refund_or_generate_a_new_key(self):
        operation = begin_dispatch(self.outbox.id, self.attempt.token)[0]
        first = mark_outcome_unknown(self.user, self.workspace.id, operation.id)
        second = mark_outcome_unknown(self.user, self.workspace.id, operation.id)
        self.assertEqual(first.status, "unknown")
        self.assertEqual(first.unknown_at, second.unknown_at)
        self.assertEqual(operation.provider_key, second.provider_key)
        self.outbox.reservation.refresh_from_db()
        self.assertEqual(self.outbox.reservation.status, "reserved")

    def test_atomic_write_failure_does_not_transition_or_leave_ledger(self):
        with patch(
            "core.dispatch.DispatchOperation.objects.create", side_effect=IntegrityError("injected")
        ):
            with self.assertRaises(IntegrityError):
                begin_dispatch(self.outbox.id, self.attempt.token)
        self.job.refresh_from_db()
        self.outbox.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("queued", 1))
        self.assertEqual(self.outbox.status, "pending")
        self.assertEqual(self.attempt.status, "leased")
        self.assertFalse(DispatchOperation.objects.exists())
        self.assertEqual(self.outbox.reservation.status, "reserved")

    def test_deadline_expiring_during_ledger_write_rolls_back(self):
        clock = SimpleNamespace(now=lambda: timezone.now() + timedelta(minutes=2))
        with patch("core.dispatch.timezone", clock):
            with self.assertRaises(RevisionConflict):
                begin_dispatch(self.outbox.id, self.attempt.token)
        self.assertFalse(DispatchOperation.objects.exists())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "queued")

    def test_expired_and_revoked_preflight_cannot_start(self):
        JobAttempt.objects.filter(pk=self.attempt.id).update(expires_at=timezone.now())
        with self.assertRaises(RevisionConflict):
            begin_dispatch(self.outbox.id, self.attempt.token)
        self.assertFalse(DispatchOperation.objects.exists())
        self.attempt = claim_pre_dispatch(self.outbox.id)
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        with self.assertRaises(Http404):
            begin_dispatch(self.outbox.id, self.attempt.token)
        self.assertFalse(DispatchOperation.objects.exists())

    def test_tenant_viewer_unknown_and_snapshot_boundaries(self):
        operation = begin_dispatch(self.outbox.id, self.attempt.token)[0]
        other = User.objects.create_user(username="dispatch-other")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        with self.assertRaises(Http404):
            mark_outcome_unknown(other, foreign.id, operation.id)
        with self.assertRaises(Http404):
            dispatch_snapshot(other, foreign.id, self.outbox.id)
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertEqual(len(dispatch_snapshot(self.user, self.workspace.id, self.outbox.id)), 1)
        with self.assertRaises(PermissionDenied):
            mark_outcome_unknown(self.user, self.workspace.id, operation.id)
        self.assertEqual(self.client.get("/health/").json()["provider_dispatch"], False)

    def test_rollback_guard_preserves_started_evidence(self):
        migration = importlib.import_module("core.migrations.0008_dispatch_write_ahead")
        editor = connection.schema_editor(atomic=False)
        migration.protect_uncertain_rollback(apps, editor)
        begin_dispatch(self.outbox.id, self.attempt.token)
        with self.assertRaisesRegex(RuntimeError, "Dispatch evidence exists"):
            migration.protect_uncertain_rollback(apps, editor)
        self.assertEqual(DispatchOperation.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL row-lock verification required")
class ConcurrentDispatchTests(TransactionTestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.outbox = JobOutbox.objects.get(job=self.job)
        self.attempt = claim_pre_dispatch(self.outbox.id)

    def run_race(self, actions):
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                action()
                return "won"
            except RevisionConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, actions))

    def test_only_one_dispatch_start_commits(self):
        def action():
            begin_dispatch(self.outbox.id, self.attempt.token)

        self.assertCountEqual(self.run_race([action, action]), ["won", "conflict"])
        self.assertEqual(DispatchOperation.objects.count(), 1)
        self.outbox.reservation.refresh_from_db()
        self.assertEqual(self.outbox.reservation.status, "reserved")

    def test_dispatch_and_cancellation_serialize_without_unsafe_release(self):
        actions = [
            lambda: begin_dispatch(self.outbox.id, self.attempt.token),
            lambda: cancel_pending_job(self.user, self.workspace.id, self.job.id, 1),
        ]
        self.assertCountEqual(self.run_race(actions), ["won", "conflict"])
        self.job.refresh_from_db()
        self.outbox.reservation.refresh_from_db()
        if self.job.status == "running":
            self.assertEqual(self.outbox.reservation.status, "reserved")
            self.assertEqual(DispatchOperation.objects.count(), 1)
        else:
            self.assertEqual(self.job.status, "cancelled")
            self.assertEqual(self.outbox.reservation.status, "released")
            self.assertFalse(DispatchOperation.objects.exists())
