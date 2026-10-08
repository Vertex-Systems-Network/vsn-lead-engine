import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import PermissionDenied

from .attempts import claim_pre_dispatch
from .batch_enrollment import enroll_batch_protocol
from .dispatch import begin_dispatch
from .jobs import RevisionConflict, cancel_pending_job, enqueue_job
from .models import Entitlement, JobOutbox, Membership, SourcePolicy, User
from .services import create_workspace
from .test_jobs import fixture


@override_settings(
    SAAS_BATCH_ENROLLMENT_ENABLED=True, SAAS_BATCH_ENROLLMENT_SOURCES=frozenset({"fixture"})
)
class BatchEnrollmentTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.intent = JobOutbox.objects.get(job=self.job)

    def enroll(self):
        return enroll_batch_protocol(self.user, self.workspace.id, self.job.id, 1)

    def test_default_v2_and_disabled_empty_source_selection_fail_closed(self):
        self.assertEqual(self.intent.result_protocol, 2)
        for options in (
            {"SAAS_BATCH_ENROLLMENT_ENABLED": False},
            {"SAAS_BATCH_ENROLLMENT_SOURCES": frozenset()},
            {"SAAS_BATCH_ENROLLMENT_SOURCES": "fixture"},
        ):
            with override_settings(**options), self.assertRaises(PermissionDenied):
                self.enroll()
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.result_protocol, 2)

    def test_replay_preserves_job_revision_capacity_and_denies_dispatch(self):
        intent, created = self.enroll()
        replay, repeated = self.enroll()
        self.assertEqual(intent.pk, replay.pk)
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.job.refresh_from_db()
        self.assertEqual(
            (self.job.status, self.job.revision, self.job.result_count), ("queued", 1, 0)
        )
        intent.reservation.refresh_from_db()
        self.assertEqual(intent.reservation.status, "reserved")
        with self.assertRaises(PermissionDenied):
            claim_pre_dispatch(intent.id)
        self.assertFalse(intent.operations.exists())

    def test_any_attempt_or_started_operation_cannot_be_reclassified(self):
        attempt = claim_pre_dispatch(self.intent.id)
        with self.assertRaises(RevisionConflict):
            self.enroll()
        begin_dispatch(self.intent.id, attempt.token)
        with self.assertRaises(RevisionConflict):
            self.enroll()
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.result_protocol, 2)

    def test_current_admin_active_actor_and_tenant_are_required(self):
        for role in ("member", "viewer"):
            Membership.objects.filter(user=self.user, workspace=self.workspace).update(role=role)
            with self.assertRaises(PermissionDenied):
                self.enroll()
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="owner")
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.enroll()
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        other = User.objects.create_user(username="foreign-enrollment")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        from django.http import Http404

        with self.assertRaises(Http404):
            enroll_batch_protocol(other, foreign.id, self.job.id, 1)

    def test_replay_rechecks_entitlement_and_source_policy(self):
        self.enroll()
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.enroll()
        Entitlement.objects.filter(workspace=self.workspace).update(active=True)
        SourcePolicy.objects.filter(pk="fixture").update(version=2)
        with self.assertRaises(PermissionDenied):
            self.enroll()

    def test_safe_pending_cancellation_and_rollback_guard_preserve_classification(self):
        migration = importlib.import_module("core.migrations.0019_batch_protocol_selection")
        editor = SimpleNamespace(connection=connection)
        migration.protect_protocol_rollback(apps, editor)
        self.enroll()
        cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "released")
        with self.assertRaisesRegex(RuntimeError, "preservation plan"):
            migration.protect_protocol_rollback(apps, editor)

    def test_v2_receipt_candidate_and_acceptance_cannot_settle_v3_intent(self):
        from .accepted_results import accept_results
        from .receipts import reconcile_receipt
        from .result_evidence import review_candidates

        attempt = claim_pre_dispatch(self.intent.id)
        operation = begin_dispatch(self.intent.id, attempt.token)[0]
        # Synthetic corruption represents a future v3 started operation; enrollment
        # itself cannot perform this transition and current dispatch refuses v3.
        JobOutbox.objects.filter(pk=self.intent.pk).update(result_protocol=3)
        for call in (
            lambda: reconcile_receipt(self.user, self.workspace.id, operation.id, b"", ""),
            lambda: review_candidates(self.user, self.workspace.id, operation.id, b"", ""),
            lambda: accept_results(
                self.user, self.workspace.id, operation.id, b"", "", b"", "", ""
            ),
        ):
            with self.assertRaises(RevisionConflict):
                call()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "reserved")


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL enrollment/lease races required")
@override_settings(
    SAAS_BATCH_ENROLLMENT_ENABLED=True, SAAS_BATCH_ENROLLMENT_SOURCES=frozenset({"fixture"})
)
class BatchEnrollmentRaceTests(TransactionTestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.intent = JobOutbox.objects.get(job=self.job)

    def race(self, actions):
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return action()
            except (RevisionConflict, PermissionDenied):
                return "denied"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, actions))

    def enroll(self):
        return enroll_batch_protocol(self.user, self.workspace.id, self.job.id, 1)[1]

    def test_duplicate_enrollment_is_once_and_exact_replay(self):
        self.assertCountEqual(self.race([self.enroll, self.enroll]), [True, False])
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.result_protocol, 3)
        self.assertFalse(self.intent.attempts.exists())

    def test_enrollment_and_first_lease_exclude_each_other(self):
        def lease():
            claim_pre_dispatch(self.intent.id)
            return "leased"

        results = self.race([self.enroll, lease])
        self.assertIn("denied", results)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.attempts.count(), int(self.intent.result_protocol == 2))
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "reserved")
