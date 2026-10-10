"""Catalog preflight stays redacted, tenant-scoped and strictly read-only."""

from datetime import time

from django.test import TestCase

from .jobs import CONTROLS, EVIDENCE
from .models import (
    DailySchedule,
    Entitlement,
    Job,
    Membership,
    ScheduleOccurrence,
    SourcePolicy,
    User,
)
from .schedules import create_daily_schedule
from .services import create_workspace

SEARCH = {
    "countries": ["US"],
    "categories": ["Synthetic bakery"],
    "source_codes": ["synthetic-preview"],
    "required_fields": ["phone"],
}


class PlanReadinessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="readiness-owner")
        self.creator = User.objects.create_user(username="readiness-creator")
        self.viewer = User.objects.create_user(username="readiness-viewer")
        self.other = User.objects.create_user(username="readiness-outsider")
        self.workspace = create_workspace(
            self.owner, {"name": "Private readiness", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign readiness marker", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.creator, role="member")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.entitlement = Entitlement.objects.create(workspace=self.workspace, active=True)
        self.plan, _ = create_daily_schedule(
            self.creator, self.workspace.id, SEARCH, "UTC", time(8), "policy-check"
        )
        self.path = (
            f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/readiness/"
        )
        self.source = SourcePolicy.objects.create(
            code="synthetic-preview",
            version=1,
            enabled=True,
            free_collection=True,
            countries=["US"],
            categories=["Synthetic bakery"],
            statuses=["active", "closed", "opening_soon"],
            fields=["name", "phone", "website", "address"],
            evidence={key: "synthetic evidence; not verified rights" for key in EVIDENCE},
            controls={key: "synthetic control" for key in CONTROLS},
            max_provider_calls=1,
        )

    def test_internal_catalog_match_is_not_execution_certification(self):
        self.client.force_login(self.owner)
        result = self.client.get(self.path)
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        body = result.json()
        self.assertTrue(body["advisory_only"])
        self.assertEqual(body["status"], "internal_catalog_match_only")
        self.assertFalse(body["stored_enabled"])
        self.assertEqual(body["checked_source_count"], 1)
        self.assertTrue(all(check["status"] == "pass" for check in body["checks"]))
        self.assertIn("source_commercial_rights", body["unverified_execution_gates"])
        self.assertNotIn(b"synthetic evidence", result.content)
        self.assertNotIn(b"Synthetic bakery", result.content)
        self.assertNotIn(b"Foreign readiness marker", result.content)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.enabled)

    def test_missing_source_or_bad_policy_is_blocked(self):
        self.client.force_login(self.owner)
        self.source.enabled = False
        self.source.save(update_fields=["enabled"])
        blocked = self.client.get(self.path).json()
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(
            next(check["status"] for check in blocked["checks"]
                 if check["name"] == "internal_source_catalog_match"), "blocked"
        )
        self.source.enabled = True
        self.source.fields = []
        self.source.save(update_fields=["enabled", "fields"])
        self.assertEqual(self.client.get(self.path).json()["status"], "blocked")
        self.source.delete()
        self.assertEqual(self.client.get(self.path).json()["checked_source_count"], 0)

    def test_inactive_entitlement_revoked_creator_and_corrupted_snapshot(self):
        self.client.force_login(self.owner)
        self.entitlement.active = False
        self.entitlement.save(update_fields=["active"])
        self.assertEqual(self.client.get(self.path).json()["status"], "blocked")
        self.entitlement.active = True
        self.entitlement.save(update_fields=["active"])
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(
            role="viewer"
        )
        self.assertEqual(self.client.get(self.path).json()["status"], "blocked")
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(
            role="member"
        )
        DailySchedule.objects.filter(pk=self.plan.id).update(
            search={"categories": ["Private internal secret"], "extra": 1}
        )
        result = self.client.get(self.path)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "blocked")
        self.assertNotIn(b"Private internal secret", result.content)

    def test_foreign_anonymous_viewer_revoked_and_write_methods_denied(self):
        anonymous = self.client.get(self.path)
        self.assertIn(anonymous.status_code, (401, 403))
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.force_login(self.owner)
        for query in ("?debug=true", "?refresh=1", "?source=synthetic-preview"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.path + query).status_code, 400)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.path).status_code, 405)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
