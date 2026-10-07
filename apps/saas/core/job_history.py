"""Read-only tenant snapshots with bounded, signed chronological continuation."""

from datetime import datetime
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.timezone import is_aware

from .models import Job, Workspace
from .services import membership_for

PAGE_SIZE = 25
CURSOR_SALT = "saas.job-history.v1"


class InvalidHistoryCursor(ValueError):
    pass


def decode_cursor(cursor, workspace_id):
    try:
        if len(cursor) > 1024:
            raise ValueError
        data = signing.loads(cursor, salt=CURSOR_SALT, max_age=86400)
        if not isinstance(data, dict) or set(data) != {"workspace", "created", "id"}:
            raise ValueError
        if data["workspace"] != str(workspace_id):
            raise ValueError
        created = datetime.fromisoformat(data["created"])
        if not is_aware(created):
            raise ValueError
        return created, UUID(data["id"])
    except (signing.BadSignature, ValueError, TypeError, KeyError, AttributeError):
        raise InvalidHistoryCursor("Invalid or expired job history continuation.") from None


def locked_workspace(user, workspace_id):
    membership_for(user, workspace_id)
    workspace = Workspace.objects.select_for_update().get(pk=workspace_id)
    membership_for(user, workspace_id, lock=True)
    return workspace


@transaction.atomic
def history_snapshot(user, workspace_id, cursor=None):
    workspace = locked_workspace(user, workspace_id)
    query = Job.objects.filter(workspace_id=workspace_id).order_by("-created_at", "-id")
    if cursor is not None:
        created, job_id = decode_cursor(cursor, workspace_id)
        query = query.filter(Q(created_at__lt=created) | Q(created_at=created, id__lt=job_id))
    rows = list(query[: PAGE_SIZE + 1])
    next_cursor = None
    if len(rows) > PAGE_SIZE:
        last = rows[PAGE_SIZE - 1]
        next_cursor = signing.dumps(
            {
                "workspace": str(workspace_id),
                "created": last.created_at.isoformat(),
                "id": str(last.id),
            },
            salt=CURSOR_SALT,
        )
    return workspace, rows[:PAGE_SIZE], next_cursor


@transaction.atomic
def detail_snapshot(user, workspace_id, job_id):
    workspace = locked_workspace(user, workspace_id)
    job = get_object_or_404(Job, workspace_id=workspace_id, pk=job_id)
    return workspace, job
