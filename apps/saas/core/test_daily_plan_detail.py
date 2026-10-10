"""Read-only daily plan detail remains scoped and non-mutating."""

from datetime import time

from django.test import TestCase

from .models import DailySchedule, Job, Membership, ScheduleOccurrence, User
from .serializers import SearchSerializer
from .services import create_workspace


class DailyPlanDetailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="plan-detail-owner")
        self.viewer = User.objects.create_user(username="plan-detail-viewer")
        self.other = User.objects.create_user(username="plan-detail-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Detail private workspace", "timezone": "America/Toronto"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign private workspace", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        serializer = SearchSerializer(
            data={
                "countries": ["US", "CA"],
                "categories": ["Synthetic bakery"],
                "statuses": ["active"],
                "required_fields": ["phone", "website"],
                "source_codes": ["overture"],
                "result_limit": 25,
            }
        )
        serializer.is_valid(raise_exception=True)
        self.plan = DailySchedule.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            key="scoped-detail",
            timezone="America/Toronto",
            local_time=time(8, 30),
            search=serializer.validated_data,
            request_hash="a" * 64,
            enabled=False,
        )
        self.foreign_plan = DailySchedule.objects.create(
            workspace=self.foreign,
            created_by=self.other,
            key="foreign-detail",
            timezone="UTC",
            local_time=time(10, 0),
            search=serializer.validated_data,
            request_hash="b" * 64,
            enabled=False,
        )
        self.path = f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/"

    def test_owner_and_viewer_read_only_normalized_scope(self):
        for actor in (self.owner, self.viewer):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                response = self.client.get(self.path)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["id"], str(self.plan.id))
                self.assertEqual(body["workspace_id"], str(self.workspace.id))
                self.assertEqual(body["search"]["countries"], ["CA", "US"])
                self.assertEqual(body["search"]["categories"], ["Synthetic bakery"])
                self.assertEqual(body["search"]["statuses"], ["active"])
                self.assertEqual(body["search"]["source_codes"], ["overture"])
                self.assertEqual(body["search"]["result_limit"], 25)
                self.assertEqual(body["local_time"], "08:30")
                self.assertFalse(body["enabled"])
                self.assertNotIn("request_hash", body)
                self.assertNotIn("created_by", body)
                self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(DailySchedule.objects.count(), 2)
        self.assertFalse(ScheduleOccurrence.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_anonymous_foreign_cross_workspace_and_revoked_denial(self):
        anon = self.client.get(self.path)
        self.assertIn(anon.status_code, (401, 403))
        self.assertNotIn(b"Synthetic bakery", anon.content)
        self.client.force_login(self.other)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"Synthetic bakery", response.content)
        self.client.force_login(self.owner)
        other_id = self.foreign_plan.id
        swapped = self.client.get(
            f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{other_id}/"
        )
        self.assertEqual(swapped.status_code, 404)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_unsupported_query_and_all_write_methods_are_denied(self):
        self.client.force_login(self.owner)
        for params in ("?fields=private", "?activate=1", "?page=2"):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.path + params).status_code, 400)
        for verb in ("post", "put", "patch", "delete"):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(self.path, {"enabled": True})
                self.assertEqual(response.status_code, 405)
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.enabled)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_invalid_saved_search_fails_closed_without_echoing_internal_payload(self):
        self.client.force_login(self.owner)
        self.plan.search = {"categories": ["Synthetic secret"], "extra_field": "Internal"}
        self.plan.save(update_fields=["search"])
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b"Internal", response.content)
