"""Bounded saved-job state filtering, separate from requested business status."""

from uuid import UUID

from rest_framework.exceptions import ValidationError

from .models import Job

JOB_STATES = ("draft", "queued", "running", "partial", "completed", "failed", "paused", "cancelled")


def job_page(workspace_id, params):
    if set(params) - {"after", "status"} or any(len(params.getlist(key)) != 1 for key in params):
        raise ValidationError("Unsupported or repeated job query parameter.")
    query = Job.objects.filter(workspace_id=workspace_id).order_by("id")
    if "status" in params:
        value = params["status"]
        if value not in JOB_STATES:
            raise ValidationError({"status": "Choose a supported job state."})
        query = query.filter(status=value)
    if "after" in params:
        try:
            after = UUID(params["after"])
        except (ValueError, AttributeError):
            raise ValidationError({"after": "Invalid continuation cursor."}) from None
        query = query.filter(id__gt=after)
    rows = list(query[:26])
    return rows[:25], str(rows[24].id) if len(rows) > 25 else None
