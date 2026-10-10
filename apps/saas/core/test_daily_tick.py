"""Default-off daily tick, fixture-only opt-in, and no provider/queue effects."""

import json
import os
from datetime import UTC, datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from .daily_plan_pause import pause_daily_schedule
from .daily_tick import tick_daily_plans
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

NOW = datetime(2026, 11, 1, 16, tzinfo=UTC)
FIXTURE_SEARCH = {
    "countries": ["US"],
    "categories": ["Synthetic test-only"],
    "source_codes": ["local-fixture"],
}
NON_FIXTURE_SEARCH = {
    "countries": ["US"],
    "categories": ["Synthetic test-only"],
    "source_codes": ["overture"],
}


class DailyTickTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="tick-owner")
        self.viewer = User.objects.create_user(username="tick-viewer")
        self.other = User.objects.create_user(username="tick-other")
        self.workspace = create_workspace(
            self.owner, {"name": "Private tick", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign hidden tick", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        Entitlement.objects.create(workspace=self.workspace, active=True, job_limit=100)
        self.plan, _ = create_daily_schedule(
            self.owner,
            self.workspace.id,
            FIXTURE_SEARCH,
            "America/New_York",
            time(1, 30),
            "fixture-daily",
        )

    def tick(self, actor=None, **kwargs):
        with (
            patch("core.daily_due_diagnostics.timezone.now", return_value=NOW),
            patch("core.schedules.timezone.now", return_value=NOW),
        ):
            return tick_daily_plans(actor or self.owner, self.workspace.id, **kwargs)

    def allow_fixture(self):
        return override_settings(
            DEBUG=True,
            SAAS_LOCAL_FULFILMENT=True,
            SAAS_FULFILMENT_SOURCES=["local-fixture"],
        )

    def test_default_disabled_preview_no_rows_or_writes(self):
        report = self.tick()
        self.assertEqual(report["mode"], "dry_run")
        self.assertTrue(report["advisory_only"])
        self.assertEqual(report["inspected_plans"], 1)
        self.assertEqual(report["considered_dates"], 0)
        self.assertEqual(report["created_drafts"], 0)
        self.assertFalse(report["dispatch_performed"])
        self.assertFalse(report["automatic_recurrence"])
        self.assertEqual(report["provider_calls"], 0)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_synthetic_enabled_preview_is_still_read_only_and_redacted(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        report = self.tick()
        self.assertEqual(report["plans"][0]["diagnostic_status"],
                         "candidate_due_requires_execution_gates")
        self.assertEqual(report["considered_dates"], 7)
        self.assertEqual(report["created_drafts"], 0)
        self.assertEqual(report["plans"][0]["candidate_dates"][-1], "2026-11-01")
        self.assertNotIn("Synthetic test-only", json.dumps(report))
        self.assertNotIn("local-fixture", json.dumps(report))
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_apply_is_fail_closed_without_each_explicit_development_gate(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        with self.assertRaises(PermissionDenied):
            self.tick(apply_dev=True)
        with self.allow_fixture():
            with self.assertRaises(PermissionDenied):
                self.tick(apply_dev=True)
            with patch.dict(os.environ, {"SAAS_DAILY_DEV_APPLY": "1"}):
                with override_settings(DEBUG=False):
                    with self.assertRaises(PermissionDenied):
                        self.tick(apply_dev=True)
                with override_settings(SAAS_LOCAL_FULFILMENT=False):
                    with self.assertRaises(PermissionDenied):
                        self.tick(apply_dev=True)
                with override_settings(SAAS_FULFILMENT_SOURCES=["overture"]):
                    with self.assertRaises(PermissionDenied):
                        self.tick(apply_dev=True)
        self.assertFalse(Job.objects.exists())

    def test_opted_in_dev_tick_creates_bounded_drafts_only_and_replays_idempotently(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        with self.allow_fixture(), patch.dict(os.environ, {"SAAS_DAILY_DEV_APPLY": "1"}):
            report = self.tick(apply_dev=True)
            repeat = self.tick(apply_dev=True)
        self.assertEqual(report["mode"], "development_fixture_drafts")
        self.assertEqual(report["created_drafts"], 7)
        self.assertEqual(report["plans"][0]["created_drafts"], 7)
        self.assertEqual(repeat["considered_dates"], 0)
        self.assertEqual(repeat["created_drafts"], 0)
        self.assertEqual(Job.objects.count(), 7)
        self.assertEqual(ScheduleOccurrence.objects.count(), 7)
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())
        self.assertTrue(all(job.status == "draft" for job in Job.objects.all()))
        self.plan.refresh_from_db()
        self.assertTrue(self.plan.enabled)
        self.assertEqual(self.plan.revision, 1)

    def test_non_fixture_never_writes_even_when_dev_gate_is_set(self):
        other, _ = create_daily_schedule(
            self.owner, self.workspace.id,
            NON_FIXTURE_SEARCH, "UTC", time(8), "actual-source-scope"
        )
        DailySchedule.objects.filter(pk=other.id).update(enabled=True)
        with self.allow_fixture(), patch.dict(os.environ, {"SAAS_DAILY_DEV_APPLY": "1"}):
            result = self.tick(apply_dev=True)
        row = next(item for item in result["plans"] if item["plan_id"] == str(other.id))
        self.assertEqual(row["result"], "non_fixture_source_blocked")
        self.assertEqual(row["created_drafts"], 0)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_pause_between_preview_and_materialization_is_fenced(self):
        DailySchedule.objects.filter(pk=self.plan.id).update(enabled=True)
        actual = materialize_daily

        def raced(*args, **kwargs):
            pause_daily_schedule(self.owner, self.workspace.id, self.plan.id, 1)
            return actual(*args, **kwargs)

        with (
            self.allow_fixture(),
            patch.dict(os.environ, {"SAAS_DAILY_DEV_APPLY": "1"}),
            patch("core.daily_tick.materialize_daily", side_effect=raced),
        ):
            report = self.tick(apply_dev=True)
        self.assertEqual(report["created_drafts"], 0)
        self.assertEqual(report["blocked_plans"], 1)
        self.assertEqual(report["plans"][0]["result"], "recheck_blocked")
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.enabled)
        self.assertFalse(Job.objects.exists())

    def test_current_role_tenant_and_bounds_are_enforced(self):
        with self.assertRaises(PermissionDenied):
            self.tick(actor=self.viewer)
        with self.assertRaises(Http404):
            self.tick(actor=self.other)
        for limit in (0, 6, True, "5"):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.tick(limit=limit)
        with self.assertRaises(ValidationError):
            self.tick(after="broken")
        self.assertFalse(Job.objects.exists())

    def test_bounded_paging_and_nonmutating_operator_command(self):
        for i in range(7):
            create_daily_schedule(
                self.owner, self.workspace.id,
                FIXTURE_SEARCH, "UTC", time(8), f"extra-{i}"
            )
        first = self.tick(limit=5)
        self.assertEqual(first["total_plans"], 8)
        self.assertEqual(first["inspected_plans"], 5)
        self.assertIsNotNone(first["next"])
        second = self.tick(limit=5, after=first["next"])
        self.assertEqual(second["inspected_plans"], 3)
        self.assertIsNone(second["next"])
        ids = [x["plan_id"] for x in first["plans"] + second["plans"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 8)
        out = StringIO()
        with patch("core.daily_due_diagnostics.timezone.now", return_value=NOW):
            call_command(
                "tick_daily_plans",
                actor=str(self.owner.id),
                workspace=str(self.workspace.id),
                limit=2,
                stdout=out,
            )
        command_report = json.loads(out.getvalue())
        self.assertEqual(command_report["mode"], "dry_run")
        self.assertEqual(command_report["inspected_plans"], 2)
        with self.assertRaises(CommandError):
            call_command(
                "tick_daily_plans",
                actor=str(self.viewer.id),
                workspace=str(self.workspace.id),
                apply_dev=True,
                stdout=StringIO(),
            )
        self.assertFalse(Job.objects.exists())
