"""Member-authorized, bounded and read-only daily occurrence history."""

from datetime import date

from django.http import Http404
from rest_framework.exceptions import ValidationError

from .models import DailySchedule, ScheduleOccurrence
from .services import membership_for

PAGE_SIZE = 25


def daily_occurrences_page(actor, workspace_id, plan_id, params):
    membership_for(actor, workspace_id)
    if not DailySchedule.objects.filter(id=plan_id, workspace_id=workspace_id).exists():
        raise Http404("Workspace resource not found.")
    if set(params) - {"before"} or any(len(params.getlist(k)) != 1 for k in params):
        raise ValidationError("Unsupported or repeated occurrence history parameter.")
    before = None
    if "before" in params:
        raw = params["before"]
        try:
            before = date.fromisoformat(raw)
        except (TypeError, ValueError):
            raise ValidationError({"before": "Invalid local-date history cursor."}) from None
        if before.isoformat() != raw:
            raise ValidationError({"before": "Use YYYY-MM-DD for the local-date cursor."})
    scoped = ScheduleOccurrence.objects.filter(
        schedule_id=plan_id, workspace_id=workspace_id
    )
    total = scoped.count()
    if before is not None:
        scoped = scoped.filter(local_date__lt=before)
    fetched = list(scoped.select_related("job").order_by("-local_date")[: PAGE_SIZE + 1])
    selected = fetched[:PAGE_SIZE]
    results = []
    for occurrence in selected:
        job = occurrence.job if occurrence.job_id else None
        if job is not None and job.workspace_id != workspace_id:
            raise ValidationError("Stored occurrence job requires workspace reconciliation.")
        results.append(
            {
                "id": str(occurrence.id),
                "local_date": occurrence.local_date.isoformat(),
                "local_time": occurrence.local_time.strftime("%H:%M"),
                "timezone": occurrence.timezone,
                "schedule_revision": occurrence.schedule_revision,
                "resolution": occurrence.resolution,
                "scheduled_for": occurrence.scheduled_for.isoformat()
                if occurrence.scheduled_for
                else None,
                "job_id": str(job.id) if job else None,
                "job_status": job.status if job else None,
            }
        )
    return {
        "workspace_id": str(workspace_id),
        "plan_id": str(plan_id),
        "total": total,
        "results": results,
        "next": selected[-1].local_date.isoformat() if len(fetched) > PAGE_SIZE else None,
        "advisory_only": True,
    }
