"""Scheduler candidate diagnostics do not write or authorize collection."""

import json
from datetime import UTC, datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from .daily_due_diagnostics import due_plan_diagnostics
from .models import DailySchedule, Entitlement, Job, Membership, ScheduleOccurrence, User
from .schedules import create_daily_schedule, materialize_daily
from .services import create_workspace

CLOCK = datetime(2026, 11, 1, 16, tzinfo=UTC)
SEARCH = {"countries": ["US"], "categories": ["Synthetic diagnostics only"]}


class DailyDueDiagnosticTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="due-owner")
        self.creator = User.objects.create_user(username="due-creator")
        self.viewer = User.objects.create_user(username="due-viewer")
        self.other = User.objects.create_user(username="due-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private due plan workspace", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign due plan", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.creator, role="member")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.entitlement = Entitlement.objects.create(
            workspace=self.workspace, active=True, job_limit=4
        )
        self.schedule, _ = create_daily_schedule(
            self.creator,
            self.workspace.id,
            SEARCH,
            "America/New_York",
            time(1, 30),
            "real-plan",
        )

    def inspect(self, **kwargs):
        return due_plan_diagnostics(
            self.owner, self.workspace.id, now=CLOCK, **kwargs
        )

    def test_disabled_plan_is_inert_and_diagnostic_does_not_write(self):
        report = self.inspect()
        self.assertTrue(report["advisory_only"])
        self.assertEqual(report["inspected"], 1)
        self.assertEqual(report["total_plans"], 1)
        self.assertEqual(report["plans"][0]["status"], "disabled")
        self.assertEqual(report["plans"][0]["due_local_dates"], [])
        self.assertFalse(DailySchedule.objects.get(pk=self.schedule.id).enabled)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_synthetically_enabled_due_candidate_does_not_dispatch_or_materialize(self):
        # No enabling code path is created: internal fixture update is test-only.
        DailySchedule.objects.filter(pk=self.schedule.id).update(enabled=True)
        before = self.inspect()
        plan = before["plans"][0]
        self.assertEqual(plan["status"], "candidate_due_requires_execution_gates")
        self.assertTrue(any(
            row["local_date"] == "2026-11-01" and
            row["resolution"] == "ambiguous_earlier"
            for row in plan["due_local_dates"]
        ))
        self.assertIn("source_rights", before["requires_execution_gates"])
        self.assertIn("operator_release", before["requires_execution_gates"])
        self.assertNotIn("Synthetic diagnostics only", json.dumps(before))
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
        # Internal fixture materializes one date; inspector must not recreate it.
        with patch("core.schedules.timezone.now", return_value=CLOCK):
            materialize_daily(self.owner, self.workspace.id, self.schedule.id,
                              CLOCK.date(), 1)
        snapshot = self.inspect()
        self.assertFalse(any(
            row["local_date"] == "2026-11-01"
            for row in snapshot["plans"][0]["due_local_dates"]
        ))
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(ScheduleOccurrence.objects.count(), 1)

    def test_creator_revocation_entitlement_and_tampering_fail_closed(self):
        DailySchedule.objects.filter(pk=self.schedule.id).update(enabled=True)
        self.entitlement.active = False
        self.entitlement.save(update_fields=["active"])
        self.assertEqual(self.inspect()["plans"][0]["status"], "entitlement_not_current")
        self.entitlement.active = True
        self.entitlement.save(update_fields=["active"])
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(
            role="viewer"
        )
        self.assertEqual(self.inspect()["plans"][0]["status"], "creator_not_authorized")
        Membership.objects.filter(workspace=self.workspace, user=self.creator).update(
            role="member"
        )
        DailySchedule.objects.filter(pk=self.schedule.id).update(
            search={"categories": ["Private corrupted secret"], "extra": 1}
        )
        report = self.inspect()
        self.assertEqual(report["plans"][0]["status"], "invalid_configuration")
        self.assertNotIn("Private corrupted secret", json.dumps(report))
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_tenant_role_cursor_limit_and_clock_validation(self):
        with self.assertRaises(PermissionDenied):
            due_plan_diagnostics(self.viewer, self.workspace.id, now=CLOCK)
        with self.assertRaises(Http404):
            due_plan_diagnostics(self.other, self.workspace.id, now=CLOCK)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        with self.assertRaises(Http404):
            self.inspect()
        Membership.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        for limit in (0, 26, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.inspect(limit=limit)
        with self.assertRaises(ValidationError):
            self.inspect(after="not-a-uuid")
        with self.assertRaises(ValidationError):
            due_plan_diagnostics(
                self.owner, self.workspace.id,
                now=datetime(2026, 11, 1, 16), limit=3
            )
        self.assertFalse(Job.objects.exists())

    def test_bounded_25_row_pages_and_operator_command(self):
        for number in range(28):
            DailySchedule.objects.create(
                workspace=self.workspace,
                created_by=self.creator,
                key=f"extra-{number}",
                timezone="UTC",
                local_time=time(9, 0),
                search={"countries": ["US"], "categories": ["Private"]},
                request_hash="b" * 64,
            )
        first = self.inspect()
        self.assertEqual(first["inspected"], 25)
        self.assertEqual(first["total_plans"], 29)
        self.assertIsNotNone(first["next"])
        second = self.inspect(after=first["next"])
        self.assertEqual(second["inspected"], 4)
        self.assertIsNone(second["next"])
        self.assertEqual(len({
            p["id"] for p in first["plans"] + second["plans"]
        }), 29)
        output = StringIO()
        with patch("core.daily_due_diagnostics.timezone.now", return_value=CLOCK):
            call_command(
                "inspect_daily_plans", actor=str(self.owner.pk),
                workspace=str(self.workspace.id), limit=2, stdout=output
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["inspected"], 2)
        self.assertEqual(payload["total_plans"], 29)
        self.assertTrue(payload["advisory_only"])
        with self.assertRaises(CommandError):
            call_command(
                "inspect_daily_plans", actor=str(self.viewer.pk),
                workspace=str(self.workspace.id), stdout=StringIO()
            )
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())
