import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .attempts import claim_pre_dispatch
from .dispatch import begin_dispatch, mark_outcome_unknown
from .jobs import enqueue_job
from .models import Entitlement, JobOutbox, Membership, UsageCounter, UsagePeriod, User
from .periods import advance_period
from .receipts import reconcile_receipt
from .services import IdempotencyConflict, create_workspace
from .test_jobs import fixture
from .test_receipts import VERIFIERS, proof
from .usage import release_usage, reserve_usage, settle_usage
from .usage_snapshot import usage_snapshot


class PeriodTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="periods")
        self.workspace = create_workspace(self.user, {"name": "Periods", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=self.workspace, active=True, lead_limit=10, job_limit=2
        )
        self.start = timezone.now() - timedelta(seconds=10)
        self.end = self.start + timedelta(minutes=10)

    def open(self):
        return advance_period(self.user, self.workspace.id, self.start, self.end, "first")

    def next(self):
        return advance_period(
            self.user, self.workspace.id, self.end, self.end + timedelta(minutes=10), "second"
        )

    def test_explicit_window_binds_reservation_and_api_metadata_without_automatic_reset(self):
        period = self.open()
        reservation = reserve_usage(self.user, self.workspace.id, "one", {"leads": 4})
        self.assertEqual(reservation.period_id, period.id)
        snapshot = usage_snapshot(self.user, self.workspace.id)
        self.assertEqual(snapshot["accounting"], "period_development")
        self.assertEqual(snapshot["period"]["id"], str(period.id))
        self.assertIsNone(snapshot["reset_at"])
        with patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)):
            with self.assertRaises(PermissionDenied):
                reserve_usage(self.user, self.workspace.id, "late", {"leads": 1})
            with self.assertRaises(ValidationError):
                self.next()
        self.assertEqual(UsagePeriod.objects.count(), 1)

    def test_legacy_nonzero_counters_and_outstanding_capacity_block_initial_period(self):
        reservation = reserve_usage(self.user, self.workspace.id, "legacy", {"leads": 4})
        with self.assertRaises(ValidationError):
            self.open()
        settle_usage(self.user, self.workspace.id, reservation.id, {"leads": 3})
        with self.assertRaises(ValidationError):
            self.open()
        self.assertFalse(UsagePeriod.objects.exists())
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 3)

    def test_rollover_archives_closed_totals_and_replay_never_resets_twice(self):
        first = self.open()
        self.assertEqual(self.open().id, first.id)
        reservation = reserve_usage(self.user, self.workspace.id, "use", {"leads": 5})
        settle_usage(self.user, self.workspace.id, reservation.id, {"leads": 3})
        with patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)):
            second = self.next()
            self.assertEqual(self.next().id, second.id)
            reserve_usage(self.user, self.workspace.id, "new-use", {"leads": 2})
            self.assertEqual(self.open().id, first.id)
        first.refresh_from_db()
        self.assertEqual((first.status, first.settled_snapshot["leads"]), ("closed", 3))
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertEqual((counter.period_id, counter.leads), (second.id, 0))
        reservation.refresh_from_db()
        self.assertEqual(reservation.period_id, first.id)
        self.assertEqual(
            usage_snapshot(self.user, self.workspace.id)["counters"]["leads"]["reserved"], 2
        )

    def test_invalid_boundaries_role_revocation_and_changed_key_payload_are_rejected(self):
        for start, end in [
            (self.start.replace(tzinfo=None), self.end),
            (self.end, self.start),
            (self.start, self.start + timedelta(days=367)),
            (self.end, self.end + timedelta(days=1)),
        ]:
            with self.assertRaises(ValidationError):
                advance_period(self.user, self.workspace.id, start, end, "bad")
        self.open()
        with self.assertRaises(IdempotencyConflict):
            advance_period(
                self.user, self.workspace.id, self.start, self.end + timedelta(seconds=1), "first"
            )
        for role in ["member", "viewer"]:
            Membership.objects.filter(workspace=self.workspace, user=self.user).update(role=role)
            with self.assertRaises(PermissionDenied):
                self.open()
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        with self.assertRaises(Http404):
            self.open()

    def test_failed_rollover_is_atomic_and_reverse_guard_preserves_history(self):
        self.open()
        with (
            patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)),
            patch(
                "core.periods.UsagePeriod.objects.create", side_effect=IntegrityError("injected")
            ),
        ):
            with self.assertRaises(IntegrityError):
                self.next()
        self.assertEqual(UsagePeriod.objects.filter(status="open").count(), 1)
        self.assertFalse(UsagePeriod.objects.filter(status="closed").exists())
        guard = importlib.import_module(
            "core.migrations.0010_usage_periods"
        ).protect_period_rollback
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))

    def test_release_pending_usage_allows_expired_rollover_but_no_early_reset(self):
        self.open()
        with self.assertRaises(ValidationError):
            self.next()
        reservation = reserve_usage(self.user, self.workspace.id, "pending", {"leads": 4})
        release_usage(self.user, self.workspace.id, reservation.id)
        with patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)):
            self.next()
        self.assertEqual(UsagePeriod.objects.filter(status="closed").count(), 1)

    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_started_unknown_job_blocks_rollover_until_signed_receipt_resolves(self):
        user, workspace, job = fixture()
        first = advance_period(user, workspace.id, self.start, self.end, "job-first")
        enqueue_job(user, workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        self.assertEqual(intent.expires_at, first.ends_at)
        attempt = claim_pre_dispatch(intent.id)
        operation = begin_dispatch(intent.id, attempt.token)[0]
        mark_outcome_unknown(user, workspace.id, operation.id)
        with patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)):
            with self.assertRaises(ValidationError):
                advance_period(
                    user, workspace.id, self.end, self.end + timedelta(minutes=10), "job-second"
                )
            body, signature = proof(operation)
            reconcile_receipt(user, workspace.id, operation.id, body, signature)
            second = advance_period(
                user, workspace.id, self.end, self.end + timedelta(minutes=10), "job-second"
            )
            reconcile_receipt(user, workspace.id, operation.id, body, signature)
        counter = UsageCounter.objects.get(workspace=workspace)
        self.assertEqual((counter.period_id, counter.jobs), (second.id, 0))
        first.refresh_from_db()
        self.assertEqual(first.settled_snapshot["jobs"], 1)

    def test_expired_period_blocks_pre_dispatch_even_with_a_valid_pending_intent(self):
        user, workspace, job = fixture()
        advance_period(user, workspace.id, self.start, self.end, "first")
        enqueue_job(user, workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        # Preserve a later intent deadline to prove the independent period gate.
        intent.expires_at = self.end + timedelta(hours=1)
        intent.save()
        with patch("core.periods.timezone.now", return_value=self.end + timedelta(seconds=1)):
            with self.assertRaises(PermissionDenied):
                claim_pre_dispatch(intent.id)


@skipUnless(connection.vendor == "postgresql", "Period races require real PostgreSQL locks")
class ConcurrentPeriodTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="period-race")
        self.workspace = create_workspace(self.user, {"name": "Period race", "timezone": "UTC"})
        Entitlement.objects.create(workspace=self.workspace, active=True, lead_limit=10)
        self.start = timezone.now() - timedelta(seconds=1)
        self.end = self.start + timedelta(minutes=10)

    def test_duplicate_period_start_commits_one_window(self):
        barrier = Barrier(2)

        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return advance_period(
                    User.objects.get(pk=self.user.id),
                    self.workspace.id,
                    self.start,
                    self.end,
                    "same",
                ).id
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(UsagePeriod.objects.count(), 1)

    def test_expired_rollover_and_new_reservation_share_one_workspace_lock(self):
        now = timezone.now()
        start = now - timedelta(days=2)
        end = now - timedelta(days=1)
        with patch("core.periods.timezone.now", return_value=start + timedelta(hours=1)):
            first = advance_period(self.user, self.workspace.id, start, end, "old")
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                user = User.objects.get(pk=self.user.id)
                if action == "roll":
                    advance_period(user, self.workspace.id, end, now + timedelta(days=1), "new")
                else:
                    reserve_usage(user, self.workspace.id, "racing", {"leads": 1})
                return "accepted"
            except PermissionDenied:
                return "expired"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ["roll", "reserve"]))
        self.assertEqual(results[0], "accepted")
        self.assertIn(results[1], ["accepted", "expired"])
        first.refresh_from_db()
        self.assertEqual(first.status, "closed")
        self.assertEqual(first.settled_snapshot["leads"], 0)
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertNotEqual(counter.period_id, first.id)
        from .models import UsageReservation

        self.assertFalse(
            UsageReservation.objects.filter(
                workspace=self.workspace, period=first, status="reserved"
            ).exists()
        )
