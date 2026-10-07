from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import CONTROLS, EVIDENCE, RevisionConflict, cancel_pending_job, enqueue_job
from .models import Entitlement, JobOutbox, Membership, SourcePolicy, UsageReservation, User
from .serializers import SearchSerializer
from .services import create_draft, create_workspace


def fixture():
    user = User.objects.create_user(username="outbox")
    workspace = create_workspace(user, {"name": "Outbox", "timezone": "UTC"})
    Entitlement.objects.create(
        workspace=workspace, active=True, lead_limit=20, job_limit=2, provider_call_limit=4
    )
    # Synthetic test catalog only; these strings are not real rights/approval evidence.
    SourcePolicy.objects.create(
        code="fixture",
        enabled=True,
        free_collection=True,
        countries=["US"],
        categories=["software"],
        fields=["phone"],
        evidence={key: "synthetic-test-only" for key in EVIDENCE},
        controls={key: "synthetic-test-only" for key in CONTROLS},
        max_provider_calls=2,
    )
    serializer = SearchSerializer(
        data={
            "countries": ["US"],
            "categories": ["software"],
            "source_codes": ["fixture"],
            "result_limit": 10,
        }
    )
    serializer.is_valid(raise_exception=True)
    job, _ = create_draft(user, workspace.id, serializer.validated_data, "draft")
    return user, workspace, job


class OutboxTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()

    def enqueue(self, revision=0):
        return enqueue_job(self.user, self.workspace.id, self.job.id, revision)

    def test_atomic_intent_replay_and_reserved_hard_caps(self):
        job, created = self.enqueue()
        self.assertTrue(created)
        self.assertEqual((job.status, job.revision, job.result_count), ("queued", 1, 0))
        outbox = JobOutbox.objects.get(job=job)
        self.assertEqual(outbox.reservation.status, "reserved")
        self.assertEqual(
            (outbox.reservation.leads, outbox.reservation.jobs, outbox.reservation.provider_calls),
            (10, 1, 2),
        )
        self.assertEqual(outbox.source_snapshot["fixture"]["version"], 1)
        self.assertEqual(len(outbox.source_snapshot["fixture"]["hash"]), 64)
        self.assertFalse(self.enqueue()[1])
        self.assertEqual(JobOutbox.objects.count(), 1)
        self.assertEqual(UsageReservation.objects.count(), 1)
        with self.assertRaises(RevisionConflict):
            self.enqueue(1)

    def test_partial_write_failure_rolls_back_job_budget_and_outbox(self):
        with patch("core.jobs.JobOutbox.objects.create", side_effect=IntegrityError("injected")):
            with self.assertRaises(IntegrityError):
                self.enqueue()
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("draft", 0))
        self.assertEqual(JobOutbox.objects.count(), 0)
        self.assertEqual(UsageReservation.objects.count(), 0)

    def test_policy_and_entitlement_gates_leave_no_partial_writes(self):
        policy = SourcePolicy.objects.get(pk="fixture")
        cases = [
            {"enabled": False},
            {"free_collection": False},
            {"evidence": {}},
            {"controls": {}},
            {"countries": ["CA"]},
            {"categories": []},
            {"fields": []},
            {"version": 0},
            {"max_provider_calls": 0},
            {"countries": "US"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                baseline = {key: getattr(policy, key) for key in changes}
                SourcePolicy.objects.filter(pk=policy.pk).update(**changes)
                with self.assertRaises(PermissionDenied):
                    self.enqueue()
                SourcePolicy.objects.filter(pk=policy.pk).update(**baseline)
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.enqueue()
        Entitlement.objects.filter(workspace=self.workspace).update(active=True, lead_limit=9)
        with self.assertRaises(ValidationError):
            self.enqueue()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")
        self.assertEqual(UsageReservation.objects.count(), 0)
        self.assertEqual(JobOutbox.objects.count(), 0)

    def test_unknown_sources_empty_selection_and_invalid_stored_search(self):
        for sources, error in [([], ValidationError), (["unknown"], PermissionDenied)]:
            self.job.search["source_codes"] = sources
            self.job.save()
            with self.assertRaises(error):
                self.enqueue()
        self.job.search["source_codes"] = ["fixture"]
        self.job.search["client_balance"] = 999
        self.job.save()
        with self.assertRaises(ValidationError):
            self.enqueue()
        self.assertFalse(JobOutbox.objects.exists())

    def test_tenant_role_revision_and_revocation_gates(self):
        other = User.objects.create_user(username="foreign")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        with self.assertRaises(Http404):
            enqueue_job(other, foreign.id, self.job.id, 0)
        for value in (-1, True, 1.5, 2147483648):
            with self.assertRaises(ValidationError):
                self.enqueue(value)
        with self.assertRaises(RevisionConflict):
            self.enqueue(1)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            self.enqueue()
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="owner")
        self.enqueue()
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        with self.assertRaises(Http404):
            self.enqueue()

    def test_cancel_releases_only_pre_dispatch_capacity_and_replays(self):
        self.enqueue()
        for _ in range(2):
            result = cancel_pending_job(self.user, self.workspace.id, self.job.id, 1)
            self.assertEqual((result.status, result.revision), ("cancelled", 2))
        self.assertEqual(JobOutbox.objects.get(job=self.job).status, "cancelled")
        self.assertEqual(UsageReservation.objects.get().status, "released")
        with self.assertRaises(RevisionConflict):
            self.enqueue()
        with self.assertRaises(RevisionConflict):
            cancel_pending_job(self.user, self.workspace.id, self.job.id, 0)

    def test_draft_cancel_never_reserves_and_running_cancel_is_unavailable(self):
        cancel_pending_job(self.user, self.workspace.id, self.job.id, 0)
        self.assertFalse(UsageReservation.objects.exists())
        self.job.status = "running"
        self.job.revision = 3
        self.job.save()
        with self.assertRaises(RevisionConflict):
            cancel_pending_job(self.user, self.workspace.id, self.job.id, 3)


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentOutboxTests(TransactionTestCase):
    def test_duplicate_enqueue_commits_one_intent_and_reservation(self):
        user, workspace, job = fixture()
        barrier = Barrier(2)

        def submit(_):
            close_old_connections()
            try:
                actor = User.objects.get(pk=user.id)
                barrier.wait(timeout=10)
                return enqueue_job(actor, workspace.id, job.id, 0)[1]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertCountEqual(results, [True, False])
        self.assertEqual(JobOutbox.objects.count(), 1)
        self.assertEqual(UsageReservation.objects.count(), 1)

    def test_enqueue_cancel_race_has_no_orphan_intent_or_reserved_capacity(self):
        user, workspace, job = fixture()
        barrier = Barrier(2)

        def mutate(action):
            close_old_connections()
            try:
                actor = User.objects.get(pk=user.id)
                barrier.wait(timeout=10)
                try:
                    if action == "enqueue":
                        enqueue_job(actor, workspace.id, job.id, 0)
                    else:
                        cancel_pending_job(actor, workspace.id, job.id, 0)
                    return action
                except RevisionConflict:
                    return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mutate, ["enqueue", "cancel"]))
        self.assertIn("conflict", results)
        job.refresh_from_db()
        if job.status == "queued":
            self.assertEqual(UsageReservation.objects.get().status, "reserved")
            self.assertEqual(JobOutbox.objects.get().status, "pending")
        else:
            self.assertEqual(job.status, "cancelled")
            self.assertFalse(UsageReservation.objects.exists())
            self.assertFalse(JobOutbox.objects.exists())
