"""Schedule preview is DST-aware, tenant-safe and strictly non-mutating."""

from datetime import UTC, datetime, time

from django.test import TestCase

from .models import DailySchedule, Job, Membership, ScheduleOccurrence, User
from .schedule_preview import upcoming_daily_preview
from .services import create_workspace


class DailyTimeMathTests(TestCase):
    def test_gap_forward_uses_first_valid_minute_not_utc_guess(self):
        now = datetime(2027, 3, 13, 15, 0, tzinfo=UTC)
        rows = upcoming_daily_preview("America/New_York", time(2, 30), now=now)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["local_date"], "2027-03-14")
        self.assertEqual(rows[0]["resolved_local_time"], "03:00")
        self.assertEqual(rows[0]["utc_instant"], "2027-03-14 07:00 UTC")
        self.assertEqual(rows[0]["offset"], "UTC-04:00")
        self.assertEqual(rows[0]["resolution"], "gap_forward")
        self.assertEqual(rows[1]["resolution"], "normal")

    def test_ambiguous_fall_back_chooses_earlier_utc_instant(self):
        now = datetime(2027, 11, 6, 18, 0, tzinfo=UTC)
        rows = upcoming_daily_preview("America/New_York", time(1, 30), now=now)
        self.assertEqual(rows[0]["local_date"], "2027-11-07")
        self.assertEqual(rows[0]["utc_instant"], "2027-11-07 05:30 UTC")
        self.assertEqual(rows[0]["offset"], "UTC-04:00")
        self.assertEqual(rows[0]["resolution"], "ambiguous_earlier")
        self.assertEqual(rows[1]["offset"], "UTC-05:00")

    def test_not_yet_due_includes_current_local_day(self):
        now = datetime(2027, 5, 1, 10, 0, tzinfo=UTC)
        rows = upcoming_daily_preview("America/Toronto", time(8, 0), now=now)
        self.assertEqual(rows[0]["local_date"], "2027-05-01")
        self.assertEqual(rows[0]["utc_instant"], "2027-05-01 12:00 UTC")
        self.assertEqual(rows[0]["resolution"], "normal")


class DailyTimePageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="preview-owner")
        self.viewer = User.objects.create_user(username="preview-viewer")
        self.foreign_user = User.objects.create_user(username="preview-foreign")
        self.workspace = create_workspace(
            self.owner,
            {"name": "Private schedule preview", "timezone": "America/Toronto"},
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.path = f"/workspaces/{self.workspace.id}/schedule-preview/"

    def test_authorized_owner_and_viewer_see_exact_workspace_no_side_effects(self):
        for user in (self.owner, self.viewer):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Private schedule preview")
                self.assertContains(response, "Next three local-day decisions")
                self.assertContains(response, "America/Toronto")
                self.assertContains(response, "does not save a schedule")
                self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(DailySchedule.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_valid_requested_time_and_invalid_input_are_bounded(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path, {"timezone": "UTC", "time": "09:15"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "09:15")
        for params in (
            {"timezone": "Fake/Missing", "time": "09:15"},
            {"timezone": "UTC", "time": "25:00"},
            {"timezone": "UTC", "time": "09:15", "extra": "untrusted"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.path, params).status_code, 400)
        self.assertEqual(
            self.client.get(self.path + "?timezone=UTC&timezone=UTC&time=09:15").status_code,
            400,
        )
        self.assertFalse(DailySchedule.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_anonymous_foreign_revoked_and_post_are_refused(self):
        anon = self.client.get(self.path)
        self.assertEqual(anon.status_code, 302)
        self.assertNotIn(b"Private schedule preview", anon.content)
        self.client.force_login(self.foreign_user)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"Private schedule preview", response.content)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.path, {"time": "09:00"}).status_code, 405)
        self.assertFalse(DailySchedule.objects.exists())
