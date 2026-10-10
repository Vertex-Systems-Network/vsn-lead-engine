"""Workspace daily plan list must be bounded, non-mutating and tenant-safe."""

from datetime import time

from django.test import TestCase

from .models import DailySchedule, Job, Membership, ScheduleOccurrence, User
from .services import create_workspace


class DailyPlanListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="plan-list-owner")
        self.viewer = User.objects.create_user(username="plan-list-viewer")
        self.other = User.objects.create_user(username="plan-list-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Confidential plan workspace", "timezone": "America/Toronto"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign private plan", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.path = f"/api/v1/workspaces/{self.workspace.id}/daily-plans/"

    def make_plan(self, workspace, creator, number, *, enabled=False):
        return DailySchedule.objects.create(
            workspace=workspace,
            created_by=creator,
            key=f"plan-{number}",
            timezone="America/Toronto",
            local_time=time(8, 15),
            search={"countries": ["CA"], "categories": ["Private bakery marker"]},
            request_hash="a" * 64,
            enabled=enabled,
        )

    def test_empty_authorized_list_and_no_store(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "workspace_id": str(self.workspace.id),
                "total": 0,
                "results": [],
                "next": None,
            },
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_all_pages_stable_cursor_and_minimal_fields_for_viewer(self):
        for n in range(27):
            self.make_plan(self.workspace, self.owner, n, enabled=n == 8)
        self.make_plan(self.foreign, self.other, 99)
        self.client.force_login(self.viewer)
        first = self.client.get(self.path)
        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertEqual(payload["total"], 27)
        self.assertEqual(len(payload["results"]), 25)
        self.assertIsNotNone(payload["next"])
        self.assertEqual(
            set(payload["results"][0]),
            {"id", "timezone", "local_time", "enabled", "revision", "created_at"},
        )
        self.assertTrue(all(row["local_time"] == "08:15" for row in payload["results"]))
        second = self.client.get(self.path + "?after=" + payload["next"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["total"], 27)
        self.assertEqual(len(second.json()["results"]), 2)
        self.assertIsNone(second.json()["next"])
        all_rows = payload["results"] + second.json()["results"]
        self.assertEqual(len({row["id"] for row in all_rows}), 27)
        self.assertTrue(any(row["enabled"] for row in all_rows))
        self.assertNotIn(b"Foreign private plan", first.content)
        self.assertNotIn(b"Private bakery marker", first.content)
        self.assertEqual(DailySchedule.objects.count(), 28)
        self.assertFalse(ScheduleOccurrence.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_anonymous_foreign_and_revoked_access(self):
        self.make_plan(self.workspace, self.owner, 1)
        anon = self.client.get(self.path)
        self.assertIn(anon.status_code, (401, 403))
        self.assertNotIn(b"America/Toronto", anon.content)
        self.client.force_login(self.other)
        foreign = self.client.get(self.path)
        self.assertEqual(foreign.status_code, 404)
        self.assertNotIn(b"America/Toronto", foreign.content)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_repeated_invalid_or_extra_cursors_and_mutations_refused(self):
        self.client.force_login(self.owner)
        for suffix in (
            "?status=disabled",
            "?after=not-uuid",
            "?page=2",
            "?after=00000000-0000-0000-0000-000000000000&after=00000000-0000-0000-0000-000000000000",
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get(self.path + suffix).status_code, 400)
        for verb in ("post", "put", "patch", "delete"):
            with self.subTest(verb=verb):
                self.assertEqual(getattr(self.client, verb)(self.path).status_code, 405)
        self.assertFalse(DailySchedule.objects.exists())
