"""Readonly preparation receipts, not CSV delivery or download authority."""

from datetime import datetime
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .job_history import locked_workspace
from .models import Job, ResultExport
from .services import membership_for

SALT = "saas.export-history.v1"
PAGE_SIZE = 25


def continuation(value, binding):
    try:
        if type(value) is not str or not 1 <= len(value) <= 1024:
            raise ValueError
        data = signing.loads(value, salt=SALT, max_age=86400)
        if not isinstance(data, dict) or set(data) != {"binding", "created", "id"}:
            raise ValueError
        if data["binding"] != binding:
            raise ValueError
        created = datetime.fromisoformat(data["created"])
        if not timezone.is_aware(created):
            raise ValueError
        return created, UUID(data["id"])
    except (signing.BadSignature, ValueError, TypeError, KeyError, AttributeError):
        raise ValidationError(
            "Receipt continuation is invalid or expired. Open the first page."
        ) from None


@transaction.atomic
def receipt_snapshot(user, workspace_id, job_id, after=None):
    locked_workspace(user, workspace_id)
    role = membership_for(user, workspace_id).role
    if role not in {"owner", "admin", "member"}:
        raise PermissionDenied("Export preparation history is unavailable for this role.")
    if not Job.objects.filter(pk=job_id, workspace_id=workspace_id).exists():
        raise Http404("Workspace resource not found.")
    scope = "job" if role in {"owner", "admin"} else "own"
    binding = [str(user.id), str(workspace_id), str(job_id), scope]
    query = ResultExport.objects.filter(
        workspace_id=workspace_id,
        job_id=job_id,
        reservation__workspace_id=workspace_id,
        reservation__status="settled",
        reservation__exports=1,
    ).order_by("-created_at", "-id")
    if scope == "own":
        query = query.filter(created_by=user)
    if after is not None:
        created, receipt_id = continuation(after, binding)
        query = query.filter(Q(created_at__lt=created) | Q(created_at=created, id__lt=receipt_id))
    rows = list(query[: PAGE_SIZE + 1])
    cursor = None
    if len(rows) > PAGE_SIZE:
        last = rows[PAGE_SIZE - 1]
        cursor = signing.dumps(
            {"binding": binding, "created": last.created_at.isoformat(), "id": str(last.id)},
            salt=SALT,
        )
    now = timezone.now()
    return {
        "workspace_id": str(workspace_id),
        "job_id": str(job_id),
        "scope": scope,
        "receipts": [
            {
                "id": str(r.id),
                "record_count": r.record_count,
                "export_units": 1,
                "prepared_at": r.created_at.isoformat(),
                "retention_deadline": r.delete_at.isoformat(),
                "deadline_passed": r.delete_at <= now,
            }
            for r in rows[:PAGE_SIZE]
        ],
        "next_cursor": cursor,
    }


@method_decorator(never_cache, name="dispatch")
class ExportReceiptList(APIView):
    def get(self, request, workspace_id, job_id):
        membership_for(request.user, workspace_id)
        if set(request.query_params) - {"after"} or len(request.query_params.getlist("after")) > 1:
            raise ValidationError("Only one receipt continuation is available.")
        response = Response(
            receipt_snapshot(request.user, workspace_id, job_id, request.query_params.get("after"))
        )
        response["Referrer-Policy"] = "no-referrer"
        return response
