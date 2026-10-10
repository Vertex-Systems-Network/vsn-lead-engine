"""Past daily plan decisions are scoped, paginated and never runnable via history."""

from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase

from .models import (
    DailySchedule,
    Entitlement,
    Job,
    Membership,
    ScheduleOccurrence,
    User,
)
from .schedules import create_daily_schedule, materialize_daily
from .services import create_workspace


class DailyOccurrenceHistoryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="history-owner")
        self.viewer = User.objects.create_user(username="history-viewer")
        self.foreign_user = User.objects.create_user(username="history-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private occurrence history", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_user, {"name": "Foreign occurrence history", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        Entitlement.objects.create(workspace=self.workspace, active=True)
        self.plan, _ = create_daily_schedule(
            self.owner,
            self.workspace.id,
            {"countries": ["CA"], "categories": ["Synthetic history only"]},
            "America/New_York",
            time(1, 30),
            "original-plan",
        )
        self.path = (
            f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/occurrences/"
        )

    def test_empty_plan_works_for_viewer_and_is_no_store(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "workspace_id": str(self.workspace.id),
                "plan_id": str(self.plan.id),
                "total": 0,
                "results": [],
                "next": None,
                "advisory_only": True,
            },
        )
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_created_job_is_visible_even_after_safety_pause(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        now = datetime(2026, 11, 1, 16, tzinfo=UTC)
        with patch("core.schedules.timezone.now", return_value=now):
            occurrence, created = materialize_daily(
                self.owner, self.workspace.id, self.plan.id, date(2026, 11, 1), 1
            )
        self.assertTrue(created)
        self.assertEqual(occurrence.job.status, "draft")
        from .daily_plan_pause import pause_daily_schedule

        self.assertTrue(pause_daily_schedule(self.owner, self.workspace.id, self.plan.id, 1)[1])
        self.client.force_login(self.viewer)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["advisory_only"])
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["results"]), 1)
        row = data["results"][0]
        self.assertEqual(row["resolution"], "ambiguous_earlier")
        self.assertEqual(row["local_date"], "2026-11-01")
        self.assertEqual(row["job_id"], str(occurrence.job_id))
        self.assertEqual(row["job_status"], "draft")
        self.assertEqual(row["schedule_revision"], 1)
        self.assertEqual(row["timezone"], "America/New_York")
        self.assertNotIn("search", row)
        self.assertNotIn(b"Synthetic history only", response.content)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(ScheduleOccurrence.objects.count(), 1)

    def test_29_day_history_continues_by_strict_descending_local_date(self):
        start = date(2026, 8, 1)
        for i in range(29):
            ScheduleOccurrence.objects.create(
                schedule=self.plan,
                workspace=self.workspace,
                schedule_revision=1,
                local_date=start + timedelta(days=i),
                local_time=self.plan.local_time,
                timezone=self.plan.timezone,
                request_hash=self.plan.request_hash,
                resolution="skipped_day",
            )
        self.client.force_login(self.owner)
        first = self.client.get(self.path)
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(body["total"], 29)
        self.assertEqual(len(body["results"]), 25)
        self.assertEqual(body["results"][0]["local_date"], "2026-08-29")
        self.assertIsNotNone(body["next"])
        later = self.client.get(self.path + "?before=" + body["next"])
        self.assertEqual(later.status_code, 200)
        self.assertEqual(later.json()["total"], 29)
        self.assertEqual(len(later.json()["results"]), 4)
        self.assertIsNone(later.json()["next"])
        keys = [x["local_date"] for x in body["results"] + later.json()["results"]]
        self.assertEqual(len(set(keys)), 29)
        self.assertEqual(keys, sorted(keys, reverse=True))
        self.assertTrue(all(row["job_id"] is None for row in body["results"]))
        self.assertTrue(all(row["job_status"] is None for row in body["results"]))
        self.assertFalse(Job.objects.exists())
        self.assertEqual(ScheduleOccurrence.objects.count(), 29)

    def test_anonymous_foreign_swapped_plan_and_revocation_denied(self):
        anonymous = self.client.get(self.path)
        self.assertIn(anonymous.status_code, (401, 403))
        self.client.force_login(self.foreign_user)
        foreign = self.client.get(self.path)
        self.assertEqual(foreign.status_code, 404)
        self.assertNotIn(b"Private occurrence history", foreign.content)
        other_plan, _ = create_daily_schedule(
            self.foreign_user,
            self.foreign.id,
            {"countries": ["US"], "categories": ["Private foreign marker"]},
            "UTC",
            time(8),
            "foreign-plan",
        )
        self.client.force_login(self.owner)
        swapped = self.client.get(
            f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{other_plan.id}/occurrences/"
        )
        self.assertEqual(swapped.status_code, 404)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_query_mutation_and_unsupported_methods_fail_closed(self):
        self.client.force_login(self.owner)
        for query in (
            "?before=bad",
            "?before=2026-13-40",
            "?before=2026-01-01&before=2026-01-02",
            "?status=draft",
            "?limit=500",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.path + query).status_code, 400)
        for verb in ("post", "put", "patch", "delete"):
            with self.subTest(verb=verb):
                self.assertEqual(getattr(self.client, verb)(self.path).status_code, 405)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
