import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict
from .models import (
    DailySchedule,
    Job,
    JobOutbox,
    Membership,
    ScheduleOccurrence,
    UsageReservation,
    User,
)
from .schedules import create_daily_schedule, materialize_daily, resolve_daily
from .services import IdempotencyConflict, change_membership, create_draft, create_workspace

SEARCH = {"countries": ["US", "CA"], "categories": ["software"]}
NOW = datetime(2026, 11, 1, 16, tzinfo=UTC)
DAY = date(2026, 11, 1)


def fixture():
    user = User.objects.create_user(username="schedule")
    workspace = create_workspace(user, {"name": "Schedule", "timezone": "UTC"})
    schedule, _ = create_daily_schedule(
        user, workspace.id, SEARCH, "America/New_York", time(1, 30), "daily"
    )
    # Synthetic internal activation only. No activation API/timer/worker is implemented.
    DailySchedule.objects.filter(pk=schedule.id).update(enabled=True)
    return user, workspace, schedule


class ScheduleTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.schedule = fixture()

    def materialize(self, day=DAY, revision=1):
        with patch("core.schedules.timezone.now", return_value=NOW):
            return materialize_daily(self.user, self.workspace.id, self.schedule.id, day, revision)

    def test_fold_gap_half_hour_and_missing_date_resolution(self):
        instant, offset, mode = resolve_daily("America/New_York", DAY, time(1, 30))
        self.assertEqual(
            (instant, offset, mode),
            (datetime(2026, 11, 1, 5, 30, tzinfo=UTC), -14400, "ambiguous_earlier"),
        )
        self.assertEqual(
            resolve_daily("America/New_York", date(2026, 3, 8), time(2, 30)),
            (datetime(2026, 3, 8, 7, tzinfo=UTC), -14400, "gap_forward"),
        )
        self.assertEqual(
            resolve_daily("Australia/Lord_Howe", date(2026, 10, 4), time(2, 15)),
            (datetime(2026, 10, 3, 15, 30, tzinfo=UTC), 39600, "gap_forward"),
        )
        self.assertEqual(
            resolve_daily("Pacific/Apia", date(2011, 12, 30), time(8)), (None, None, "skipped_day")
        )
        self.assertEqual(
            resolve_daily("Asia/Karachi", DAY, time(8))[0], datetime(2026, 11, 1, 3, tzinfo=UTC)
        )

    def test_disabled_creation_validates_normalizes_and_replays_exact_configuration(self):
        first, created = create_daily_schedule(
            self.user, self.workspace.id, SEARCH, "UTC", time(8), "new"
        )
        self.assertTrue(created)
        self.assertFalse(first.enabled)
        self.assertEqual(first.search["required_fields"], ["phone"])
        second, created = create_daily_schedule(
            self.user, self.workspace.id, SEARCH, "UTC", time(8), "new"
        )
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        with self.assertRaises(IdempotencyConflict):
            create_daily_schedule(self.user, self.workspace.id, SEARCH, "UTC", time(9), "new")
        for zone, clock in [
            ("Unknown/Zone", time(8)),
            ("UTC", time(8, tzinfo=UTC)),
            ("UTC", time(8, 0, 1)),
        ]:
            with self.assertRaises(ValidationError):
                create_daily_schedule(self.user, self.workspace.id, SEARCH, zone, clock, "invalid")
        with self.assertRaises(ValidationError):
            create_daily_schedule(
                self.user,
                self.workspace.id,
                {**SEARCH, "countries": ["GB"]},
                "UTC",
                time(8),
                "invalid",
            )

    def test_due_fold_creates_one_draft_no_usage_and_preserves_clock_snapshot(self):
        occurrence, created = self.materialize()
        self.assertTrue(created)
        self.workspace.timezone = "Asia/Karachi"
        self.workspace.save()
        replay, created = self.materialize()
        self.assertFalse(created)
        self.assertEqual(replay.id, occurrence.id)
        self.assertEqual(
            (occurrence.job.status, occurrence.job.created_by_id), ("draft", self.user.id)
        )
        self.assertEqual(occurrence.timezone, "America/New_York")
        self.assertEqual(occurrence.resolution, "ambiguous_earlier")
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse(UsageReservation.objects.exists())
        self.assertFalse(JobOutbox.objects.exists())
        # Old exact replay is safe and does not recreate work outside catch-up bounds.
        with patch("core.schedules.timezone.now", return_value=NOW + timedelta(days=30)):
            self.assertFalse(
                materialize_daily(self.user, self.workspace.id, self.schedule.id, DAY, 1)[1]
            )

    def test_disabled_revision_corruption_foreign_and_revoked_roles_fail_closed(self):
        DailySchedule.objects.filter(pk=self.schedule.id).update(enabled=False)
        with self.assertRaises(RevisionConflict):
            self.materialize()
        DailySchedule.objects.filter(pk=self.schedule.id).update(enabled=True)
        with self.assertRaises(RevisionConflict):
            self.materialize(revision=2)
        DailySchedule.objects.filter(pk=self.schedule.id).update(
            search={**self.schedule.search, "client_budget": 99}
        )
        with self.assertRaises(ValidationError):
            self.materialize()
        DailySchedule.objects.filter(pk=self.schedule.id).update(search=self.schedule.search)
        other = User.objects.create_user(username="other")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        with self.assertRaises(Http404):
            materialize_daily(other, foreign.id, self.schedule.id, DAY, 1)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            self.materialize()
        Membership.objects.create(workspace=self.workspace, user=other, role="owner")
        with self.assertRaises(PermissionDenied):
            materialize_daily(other, self.workspace.id, self.schedule.id, DAY, 1)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        with self.assertRaises(Http404):
            materialize_daily(other, self.workspace.id, self.schedule.id, DAY, 1)
        self.assertFalse(Job.objects.exists())

    def test_future_time_old_backlog_and_non_date_rejected_without_writes(self):
        for day in [DAY + timedelta(days=1), DAY - timedelta(days=7), "2026-11-01", NOW]:
            with self.assertRaises(ValidationError):
                self.materialize(day)
        with patch(
            "core.schedules.timezone.now", return_value=datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
        ):
            with self.assertRaises(ValidationError):
                materialize_daily(self.user, self.workspace.id, self.schedule.id, DAY, 1)
        self.assertFalse(Job.objects.exists())

    def test_skipped_day_records_decision_without_job_and_gap_links_due_draft(self):
        schedule, _ = create_daily_schedule(
            self.user, self.workspace.id, SEARCH, "Pacific/Apia", time(8), "apia"
        )
        DailySchedule.objects.filter(pk=schedule.id).update(enabled=True)
        with patch(
            "core.schedules.timezone.now", return_value=datetime(2011, 12, 31, 12, tzinfo=UTC)
        ):
            occurrence, _ = materialize_daily(
                self.user, self.workspace.id, schedule.id, date(2011, 12, 30), 1
            )
        self.assertEqual(occurrence.resolution, "skipped_day")
        self.assertIsNone(occurrence.job_id)
        self.assertIsNone(occurrence.scheduled_for)
        self.assertFalse(Job.objects.exists())
        gap, _ = create_daily_schedule(
            self.user, self.workspace.id, SEARCH, "America/New_York", time(2, 30), "gap"
        )
        DailySchedule.objects.filter(pk=gap.id).update(enabled=True)
        with patch(
            "core.schedules.timezone.now", return_value=datetime(2026, 3, 8, 12, tzinfo=UTC)
        ):
            occurrence, _ = materialize_daily(
                self.user, self.workspace.id, gap.id, date(2026, 3, 8), 1
            )
        self.assertEqual(occurrence.resolution, "gap_forward")
        self.assertEqual(occurrence.local_time, time(2, 30))
        self.assertEqual(occurrence.scheduled_for.hour, 7)
        self.assertEqual(Job.objects.count(), 1)

    def test_occurrence_failure_rolls_back_draft_and_guard_preserves_schedule_history(self):
        with patch(
            "core.schedules.ScheduleOccurrence.objects.create",
            side_effect=IntegrityError("injected"),
        ):
            with self.assertRaises(IntegrityError):
                self.materialize()
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
        guard = importlib.import_module(
            "core.migrations.0011_daily_occurrences"
        ).protect_schedule_rollback
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))

    def test_preexisting_job_key_cannot_be_adopted_by_a_schedule(self):
        key = f"schedule:{self.schedule.id}:1:{DAY.isoformat()}T{self.schedule.local_time.isoformat()}"
        create_draft(self.user, self.workspace.id, self.schedule.search, key)
        with self.assertRaises(IdempotencyConflict):
            self.materialize()
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse(ScheduleOccurrence.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Occurrence races require real PostgreSQL locks")
class ConcurrentScheduleTests(TransactionTestCase):
    def test_duplicate_materialization_commits_one_occurrence_and_job(self):
        user, workspace, schedule = fixture()
        barrier = Barrier(2)

        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                occurrence, created = materialize_daily(
                    User.objects.get(pk=user.id), workspace.id, schedule.id, DAY, 1
                )
                return occurrence.id, created
            finally:
                close_old_connections()

        with (
            patch("core.schedules.timezone.now", return_value=NOW),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            results = list(pool.map(run, range(2)))
        self.assertEqual(results[0][0], results[1][0])
        self.assertCountEqual([result[1] for result in results], [True, False])
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(ScheduleOccurrence.objects.count(), 1)

    def test_creator_revocation_and_materialization_serialize_authority(self):
        user, workspace, schedule = fixture()
        owner = User.objects.create_user(username="schedule-owner")
        Membership.objects.create(workspace=workspace, user=owner, role="owner")
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                actor = User.objects.get(pk=owner.id)
                barrier.wait(timeout=10)
                if action == "revoke":
                    change_membership(actor, workspace.id, user.id, role="viewer")
                    return "revoked"
                try:
                    materialize_daily(actor, workspace.id, schedule.id, DAY, 1)
                    return "draft"
                except PermissionDenied:
                    return "denied"
            finally:
                close_old_connections()

        with (
            patch("core.schedules.timezone.now", return_value=NOW),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            results = list(pool.map(run, ["revoke", "materialize"]))
        self.assertEqual(results[0], "revoked")
        self.assertIn(results[1], ["draft", "denied"])
        self.assertEqual(Job.objects.count(), int(results[1] == "draft"))
        self.assertEqual(ScheduleOccurrence.objects.count(), Job.objects.count())
        with self.assertRaises(PermissionDenied):
            materialize_daily(owner, workspace.id, schedule.id, DAY, 1)
