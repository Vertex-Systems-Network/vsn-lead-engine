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
        self.entitlement = Entitlement.objects.create(
            workspace=self.workspace,
            active=True,
            lead_limit=100,
            job_limit=10,
            provider_call_limit=10,
        )
        self.plan, _ = create_daily_schedule(
            self.creator, self.workspace.id, SEARCH, "UTC", time(8), "policy-check"
        )
        self.path = f"/api/v1/workspaces/{self.workspace.id}/daily-plans/{self.plan.id}/readiness/"
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
        self.assertEqual(body["budget_snapshot"]["status"], "advisory_single_job_fits")
        self.assertTrue(body["budget_snapshot"]["single_job_only"])
        self.assertEqual(
            [row["name"] for row in body["budget_snapshot"]["counters"]],
            ["leads", "jobs", "provider_calls"],
        )
        self.assertEqual(body["budget_snapshot"]["counters"][0]["requested"], 100)
        self.assertEqual(body["budget_snapshot"]["counters"][1]["requested"], 1)
        self.assertEqual(body["budget_snapshot"]["counters"][2]["requested"], 1)
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
            next(
                check["status"]
                for check in blocked["checks"]
                if check["name"] == "internal_source_catalog_match"
            ),
            "blocked",
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
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(role="viewer")
        self.assertEqual(self.client.get(self.path).json()["status"], "blocked")
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(role="member")
        DailySchedule.objects.filter(pk=self.plan.id).update(
            search={"categories": ["Private internal secret"], "extra": 1}
        )
        result = self.client.get(self.path)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "blocked")
        self.assertNotIn(b"Private internal secret", result.content)

    def test_reserved_usage_and_remaining_quota_block_single_job_preflight(self):
        from .models import UsageCounter, UsageReservation

        UsageCounter.objects.create(workspace=self.workspace, leads=12, jobs=2, provider_calls=1)
        UsageReservation.objects.create(
            workspace=self.workspace,
            key="pending-test",
            request_hash="f" * 64,
            leads=5,
            jobs=1,
            provider_calls=2,
        )
        self.client.force_login(self.owner)
        result = self.client.get(self.path)
        self.assertEqual(result.status_code, 200)
        budget = result.json()["budget_snapshot"]
        self.assertEqual(budget["status"], "advisory_single_job_exceeds")
        self.assertEqual(result.json()["status"], "blocked")
        self.assertEqual(budget["counters"][0]["headroom"], 83)
        self.assertEqual(budget["counters"][0]["reserved"], 5)
        self.assertEqual(budget["counters"][1]["headroom"], 7)
        self.assertEqual(budget["counters"][2]["headroom"], 7)
        self.assertEqual(UsageReservation.objects.count(), 1)
        self.assertFalse(Job.objects.exists())

    def test_expired_accounting_window_blocks_capacity_even_when_limits_fit(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import UsageCounter, UsagePeriod

        now = timezone.now()
        period = UsagePeriod.objects.create(
            workspace=self.workspace,
            key="expired-window",
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(days=1),
        )
        UsageCounter.objects.create(workspace=self.workspace, period=period)
        self.client.force_login(self.owner)
        data = self.client.get(self.path).json()
        self.assertEqual(data["budget_snapshot"]["status"], "accounting_window_unavailable")
        self.assertEqual(data["status"], "blocked")
        self.assertFalse(Job.objects.exists())

    def test_no_usable_entitlement_or_missing_catalog_has_no_capacity_claim(self):
        self.entitlement.active = False
        self.entitlement.save(update_fields=["active"])
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(self.path).json()["budget_snapshot"]["status"], "unavailable"
        )
        self.entitlement.active = True
        self.entitlement.save(update_fields=["active"])
        self.source.delete()
        self.assertEqual(self.client.get(self.path).json()["budget_snapshot"]["counters"], [])
        self.assertFalse(Job.objects.exists())

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
