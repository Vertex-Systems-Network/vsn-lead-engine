"""Pause-only daily plans: optimistic revision, explicit CSRF and race fencing."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.http import Http404
from django.test import Client, TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied

from .daily_plan_pause import issue_pause_token, pause_daily_schedule
from .jobs import RevisionConflict
from .models import (
    DailySchedule,
    Entitlement,
    Job,
    JobOutbox,
    Membership,
    ScheduleOccurrence,
    UsageReservation,
    User,
)
from .schedules import create_daily_schedule, materialize_daily
from .services import create_workspace

SEARCH = {"countries": ["CA"], "categories": ["Synthetic pause only"]}


class DailyPlanPauseTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="pause-owner")
        self.admin = User.objects.create_user(username="pause-admin")
        self.member = User.objects.create_user(username="pause-member")
        self.viewer = User.objects.create_user(username="pause-viewer")
        self.foreign_user = User.objects.create_user(username="pause-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private pause workspace", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_user, {"name": "Foreign private pause", "timezone": "UTC"}
        )
        for actor, role in (
            (self.admin, "admin"),
            (self.member, "member"),
            (self.viewer, "viewer"),
        ):
            Membership.objects.create(workspace=self.workspace, user=actor, role=role)
        Entitlement.objects.create(workspace=self.workspace, active=True)
        self.plan, _ = create_daily_schedule(
            self.member, self.workspace.id, SEARCH, "America/Toronto", time(8, 0), "owned"
        )
        self.path = f"/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/pause/"
        self.client = Client(enforce_csrf_checks=True)

    def activate_test_only(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        self.plan.refresh_from_db()

    def payload(self, actor=None):
        actor = actor or self.owner
        self.client.force_login(actor)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "expected_revision": str(self.plan.revision),
            "pause_token": issue_pause_token(
                actor, self.workspace.id, self.plan.id, self.plan.revision
            ),
        }

    def test_default_disabled_plan_has_no_pause_form_or_write(self):
        self.client.force_login(self.owner)
        page = self.client.get(self.path)
        self.assertEqual(page.status_code, 200)
        self.assertIn("no-store", page["Cache-Control"])
        self.assertContains(page, "already disabled")
        self.assertNotContains(page, "Confirm: pause future daily occurrences")
        original, changed = pause_daily_schedule(
            self.owner, self.workspace.id, self.plan.id, 1
        )
        self.assertFalse(changed)
        self.assertEqual(original.revision, 1)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_explicit_confirm_pauses_and_fences_old_revision(self):
        self.activate_test_only()
        payload = self.payload()
        body = self.client.get(self.path)
        self.assertContains(body, "Existing saved drafts")
        self.assertContains(body, "queued/running jobs")
        response = self.client.post(self.path, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plan is disabled")
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.enabled)
        self.assertEqual(self.plan.revision, 2)
        self.assertEqual(self.plan.search["categories"], ["Synthetic pause only"])
        self.assertEqual(self.client.post(self.path, payload).status_code, 409)
        with self.assertRaises(RevisionConflict):
            pause_daily_schedule(self.owner, self.workspace.id, self.plan.id, 1)
        self.assertEqual(DailySchedule.objects.count(), 1)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())

    def test_admin_can_pause_member_created_plan(self):
        self.activate_test_only()
        payload = self.payload(self.admin)
        self.assertEqual(self.client.post(self.path, payload).status_code, 200)
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.enabled)
        self.assertEqual(self.plan.revision, 2)

    def test_member_viewer_foreign_and_revoked_denied(self):
        self.activate_test_only()
        for actor in (self.member, self.viewer):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.path).status_code, 403)
            with self.assertRaises(PermissionDenied):
                pause_daily_schedule(actor, self.workspace.id, self.plan.id, 1)
        self.client.force_login(self.foreign_user)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"Private pause workspace", response.content)
        with self.assertRaises(Http404):
            pause_daily_schedule(self.foreign_user, self.workspace.id, self.plan.id, 1)
        self.client.force_login(self.owner)
        payload = self.payload()
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.post(self.path, payload).status_code, 404)
        self.plan.refresh_from_db()
        self.assertTrue(self.plan.enabled)

    def test_csrf_anti_tamper_and_revision_race(self):
        self.activate_test_only()
        self.client.force_login(self.owner)
        raw = {
            "expected_revision": "1",
            "pause_token": issue_pause_token(
                self.owner, self.workspace.id, self.plan.id, 1
            ),
        }
        self.assertEqual(self.client.post(self.path, raw).status_code, 403)
        payload = self.payload()
        for extra in (
            {"enabled": "true"},
            {"pause_token": "forged"},
            {"expected_revision": "2"},
            {"pause_token": issue_pause_token(
                self.admin, self.workspace.id, self.plan.id, 1
            )},
        ):
            with self.subTest(extra=extra):
                status = self.client.post(self.path, {**payload, **extra}).status_code
                self.assertEqual(status, 400)
        self.assertEqual(self.client.get(self.path + "?enabled=true").status_code, 400)
        self.assertEqual(self.client.put(self.path).status_code, 405)
        DailySchedule.objects.filter(pk=self.plan.id).update(revision=2)
        self.assertEqual(self.client.post(self.path, payload).status_code, 409)
        self.plan.refresh_from_db()
        self.assertTrue(self.plan.enabled)
        self.assertFalse(Job.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Concurrency requires PostgreSQL row locks")
class DailyPauseMaterializeRaceTests(TransactionTestCase):
    def test_pause_serializes_with_due_materialization(self):
        owner = User.objects.create_user(username="race-pause-owner")
        ws = create_workspace(owner, {"name": "Pause race", "timezone": "UTC"})
        Entitlement.objects.create(workspace=ws, active=True)
        plan, _ = create_daily_schedule(
            owner, ws.id, SEARCH, "America/New_York", time(1, 30), "pause-race"
        )
        DailySchedule.objects.filter(pk=plan.id).update(enabled=True)
        now = datetime(2026, 11, 1, 16, tzinfo=UTC)
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                actor = User.objects.get(pk=owner.pk)
                barrier.wait(timeout=10)
                if action == "pause":
                    return pause_daily_schedule(actor, ws.id, plan.id, 1)[1]
                try:
                    return materialize_daily(actor, ws.id, plan.id, date(2026, 11, 1), 1)[1]
                except RevisionConflict:
                    return "fenced"
            finally:
                close_old_connections()

        with (
            patch("core.schedules.timezone.now", return_value=now),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            paused, outcome = pool.map(run, ("pause", "materialize"))
        self.assertTrue(paused)
        self.assertIn(outcome, (True, "fenced"))
        plan.refresh_from_db()
        self.assertFalse(plan.enabled)
        self.assertEqual(plan.revision, 2)
        self.assertEqual(Job.objects.count(), int(outcome is True))
        self.assertEqual(ScheduleOccurrence.objects.count(), Job.objects.count())
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())
        with patch("core.schedules.timezone.now", return_value=now):
            with self.assertRaises(RevisionConflict):
                materialize_daily(owner, ws.id, plan.id, date(2026, 11, 1), 1)
