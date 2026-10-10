"""Daily plan stop is owner-only, CSRF-protected and revision-fenced."""

from datetime import time
from unittest.mock import patch

from django.http import Http404
from django.test import Client, TestCase
from rest_framework.exceptions import PermissionDenied

from .daily_plan_stop_forms import new_stop_token
from .jobs import RevisionConflict
from .models import DailySchedule, Entitlement, Job, Membership, ScheduleOccurrence, User
from .schedules import create_daily_schedule, disable_daily_schedule, materialize_daily
from .services import create_workspace

SEARCH = {"countries": ["US"], "categories": ["Synthetic stop test"]}


class DailyPlanStopTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="stop-owner")
        self.admin = User.objects.create_user(username="stop-admin")
        self.viewer = User.objects.create_user(username="stop-viewer")
        self.other = User.objects.create_user(username="stop-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private emergency stop", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign emergency stop", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.admin, role="admin")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        Entitlement.objects.create(workspace=self.workspace, active=True, job_limit=10)
        self.plan, _ = create_daily_schedule(
            self.owner, self.workspace.id, SEARCH, "UTC", time(8, 0), "stop-key"
        )
        self.path = f"/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/stop/"

    def enable_fixture(self):
        # Only a test fixture; user activation remains unavailable.
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        self.plan.refresh_from_db()

    def test_atomic_stop_fences_stale_scheduler_and_leaves_jobs_untouched(self):
        self.enable_fixture()
        stopped, changed = disable_daily_schedule(
            self.owner, self.workspace.id, self.plan.id, self.plan.revision
        )
        self.assertTrue(changed)
        self.assertFalse(stopped.enabled)
        self.assertEqual(stopped.revision, 2)
        with self.assertRaises(RevisionConflict):
            disable_daily_schedule(self.owner, self.workspace.id, self.plan.id, 1)
        retry, changed = disable_daily_schedule(self.admin, self.workspace.id, self.plan.id, 2)
        self.assertFalse(changed)
        self.assertEqual(retry.revision, 2)
        with self.assertRaises(RevisionConflict):
            materialize_daily(
                self.owner, self.workspace.id, self.plan.id, self.plan.created_at.date(), 1
            )
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_owner_role_workspace_and_revocation_fences(self):
        self.enable_fixture()
        with self.assertRaises(PermissionDenied):
            disable_daily_schedule(self.viewer, self.workspace.id, self.plan.id, 1)
        with self.assertRaises(Http404):
            disable_daily_schedule(self.other, self.workspace.id, self.plan.id, 1)
        with self.assertRaises(Http404):
            disable_daily_schedule(self.owner, self.foreign.id, self.plan.id, 1)
        self.assertTrue(DailySchedule.objects.get(pk=self.plan.id).enabled)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        with self.assertRaises(Http404):
            disable_daily_schedule(self.owner, self.workspace.id, self.plan.id, 1)
        self.assertTrue(DailySchedule.objects.get(pk=self.plan.id).enabled)

    def test_explicit_browser_csrf_stop_and_stale_replay(self):
        self.enable_fixture()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        get = client.get(self.path)
        self.assertEqual(get.status_code, 200)
        self.assertContains(get, "Confirm stop of this daily plan")
        self.assertContains(get, "does not cancel drafts")
        self.assertIn("no-store", get["Cache-Control"])
        payload = {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            "stop_token": new_stop_token(self.admin, self.workspace.id, self.plan.id, 1),
        }
        self.assertEqual(
            client.post(self.path, {"stop_token": payload["stop_token"]}).status_code, 403
        )
        success = client.post(self.path, payload)
        self.assertEqual(success.status_code, 200)
        self.assertContains(success, "Daily plan disabled")
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.revision, 2)
        self.assertFalse(self.plan.enabled)
        self.assertEqual(client.post(self.path, payload).status_code, 409)
        self.assertEqual(client.get(self.path).status_code, 200)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_foreign_tampered_invalid_and_disabled_form(self):
        self.enable_fixture()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.get(self.path)
        token = new_stop_token(self.owner, self.workspace.id, self.plan.id, 1)
        payload = {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            "stop_token": token,
        }
        for changes in (
            {"stop_token": "forged"},
            {"stop_token": new_stop_token(self.other, self.workspace.id, self.plan.id, 1)},
            {"enabled": "true"},
            {"revision": "1"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(client.post(self.path, {**payload, **changes}).status_code, 400)
        self.assertEqual(client.get(self.path + "?activate=1").status_code, 400)
        self.assertEqual(client.put(self.path, payload).status_code, 405)
        client.force_login(self.viewer)
        self.assertEqual(client.get(self.path).status_code, 403)
        client.force_login(self.other)
        self.assertEqual(client.get(self.path).status_code, 404)
        self.assertTrue(DailySchedule.objects.get(pk=self.plan.id).enabled)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_expired_signed_token_is_rejected(self):
        self.enable_fixture()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.get(self.path)
        with patch("django.core.signing.time.time", return_value=1):
            stale = new_stop_token(self.owner, self.workspace.id, self.plan.id, 1)
        payload = {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            "stop_token": stale,
        }
        self.assertEqual(client.post(self.path, payload).status_code, 400)
        self.assertTrue(DailySchedule.objects.get(pk=self.plan.id).enabled)
