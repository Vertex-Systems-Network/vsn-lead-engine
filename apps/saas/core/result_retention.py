"""Explicit bounded source-deadline payload erasure; fingerprints remain tombstones."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .job_history import locked_workspace
from .models import AcceptedResult
from .services import membership_for


@transaction.atomic
def expire_result_payloads(user, workspace_id, *, limit=100):
    locked_workspace(user, workspace_id)
    member = membership_for(user, workspace_id, lock=True)
    if member.role not in {"owner", "admin"}:
        raise PermissionDenied("Only current workspace administrators may erase expired payloads.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("Choose a cleanup limit from 1 to 100.")
    now = timezone.now()
    due = AcceptedResult.objects.filter(
        workspace_id=workspace_id, erased_at__isnull=True, delete_at__lte=now
    )
    rows = list(due.select_for_update().order_by("delete_at", "id")[:limit])
    # Multiple null references preserve the original batch uniqueness constraint;
    # no personal/source record identifier survives in the tombstone payload.
    if rows:
        AcceptedResult.objects.filter(
            workspace_id=workspace_id, id__in=[row.id for row in rows]
        ).update(
            fields={},
            field_lineage={},
            record_ref=None,
            category="",
            purpose="",
            retention_version="",
            erased_at=now,
            erased_by=user,
        )
    return {"erased_count": len(rows), "more_due": due.exists()}
