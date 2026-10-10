"""Bounded, dry-run-first daily tick with strictly fixture-only development writes.

No production scheduling, recurrence activation, enqueue, source request or
billing activity is provided by this module.
"""

import os
from datetime import date

from django.conf import settings
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .daily_due_diagnostics import due_plan_diagnostics
from .jobs import RevisionConflict
from .models import DailySchedule
from .schedules import materialize_daily
from .services import IdempotencyConflict

MAX_PLANS = 5
MAX_DAYS_PER_PLAN = 7
DEV_APPLY_FLAG = "SAAS_DAILY_DEV_APPLY"


def development_apply_allowed():
    """Never allow plan-to-draft writes in any non-debug or real-source mode."""
    return (
        settings.DEBUG is True
        and settings.SAAS_LOCAL_FULFILMENT is True
        and "local-fixture" in settings.SAAS_FULFILMENT_SOURCES
        and os.environ.get(DEV_APPLY_FLAG) == "1"
    )


def tick_daily_plans(actor, workspace_id, *, limit=5, after=None, apply_dev=False):
    """Plan at most five schedules; optional fixture-only drafts are individually fenced."""
    if type(limit) is not int or not 1 <= limit <= MAX_PLANS:
        raise ValidationError("Daily tick limit must be between 1 and 5 plans.")
    if type(apply_dev) is not bool:
        raise ValidationError("Explicit boolean apply mode required.")
    if apply_dev and not development_apply_allowed():
        raise PermissionDenied("Development fixture-only daily tick is not authorized.")

    snapshot = due_plan_diagnostics(actor, workspace_id, limit=limit, after=after)
    rows = []
    created_drafts = 0
    skipped_existing = 0
    blocked = 0
    considered_dates = 0

    for item in snapshot["plans"]:
        candidate_dates = item["due_local_dates"]
        record = {
            "plan_id": item["id"],
            "revision": item["revision"],
            "diagnostic_status": item["status"],
            "candidate_dates": [day["local_date"] for day in candidate_dates],
            "created_drafts": 0,
            "already_recorded": 0,
            "result": "no_due_dates" if not candidate_dates else "preview_only",
        }
        considered_dates += len(candidate_dates)
        if len(candidate_dates) > MAX_DAYS_PER_PLAN:
            raise ValidationError("Diagnostic exceeded bounded catch-up window.")
        if apply_dev and candidate_dates:
            # This is an advisory read; materialize_daily obtains fresh workspace,
            # membership, schedule/revision and entitlement locks for every date.
            plan = DailySchedule.objects.filter(
                pk=item["id"], workspace_id=workspace_id
            ).only("search").first()
            if plan is None:
                record["result"] = "recheck_blocked"
                blocked += 1
            elif plan.search.get("source_codes") != ["local-fixture"]:
                record["result"] = "non_fixture_source_blocked"
                blocked += 1
            else:
                record["result"] = "development_fixture_only"
                for local_day in candidate_dates:
                    try:
                        _, was_created = materialize_daily(
                            actor,
                            workspace_id,
                            item["id"],
                            date.fromisoformat(local_day["local_date"]),
                            item["revision"],
                        )
                    except (
                        Http404,
                        PermissionDenied,
                        ValidationError,
                        RevisionConflict,
                        IdempotencyConflict,
                    ):
                        # A fresh revocation, pause, expired entitlement or
                        # duplicate is NOT an invitation to bypass execution gates.
                        record["result"] = "recheck_blocked"
                        blocked += 1
                        break
                    if was_created:
                        created_drafts += 1
                        record["created_drafts"] += 1
                    else:
                        skipped_existing += 1
                        record["already_recorded"] += 1
        rows.append(record)

    return {
        "workspace_id": str(workspace_id),
        "as_of_utc": snapshot["as_of_utc"],
        "mode": "development_fixture_drafts" if apply_dev else "dry_run",
        "advisory_only": not apply_dev,
        "inspected_plans": snapshot["inspected"],
        "total_plans": snapshot["total_plans"],
        "next": snapshot["next"],
        "considered_dates": considered_dates,
        "created_drafts": created_drafts,
        "already_recorded": skipped_existing,
        "blocked_plans": blocked,
        "max_plans": MAX_PLANS,
        "max_days_per_plan": MAX_DAYS_PER_PLAN,
        "dispatch_performed": False,
        "provider_calls": 0,
        "automatic_recurrence": False,
        "plans": rows,
    }
