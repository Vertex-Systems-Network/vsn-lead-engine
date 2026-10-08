"""Signed bounded Next export confirmation. Django owns CSV preparation and CSRF."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .form_context import form_csrf
from .models import Entitlement, SourcePolicy, UsageCounter, UsageReservation
from .periods import active_window
from .result_exports import FIELD_ORDER, export_rights, prepare_export, specification
from .result_query import results_snapshot
from .services import membership_for
from .usage import lock_workspace

SALT = "saas.export-confirmation.v1"


@transaction.atomic
def export_context(user, workspace_id, job_id):
    lock_workspace(user, workspace_id)
    entitlement = Entitlement.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.active or entitlement.export_limit < 1:
        raise PermissionDenied("Export entitlement is unavailable.")
    counter = UsageCounter.objects.filter(workspace_id=workspace_id).first()
    if counter is None:
        raise PermissionDenied("Export accounting is unavailable.")
    active_window(counter)
    pending = (
        UsageReservation.objects.filter(workspace_id=workspace_id, status="reserved").aggregate(
            total=Sum("exports")
        )["total"]
        or 0
    )
    if counter.exports + pending >= entitlement.export_limit:
        raise PermissionDenied("Export budget is unavailable.")
    snapshot = results_snapshot(user, workspace_id, job_id)
    rows = snapshot["results"]
    if not rows:
        raise PermissionDenied("No current results are available for export.")
    allowed = set(FIELD_ORDER)
    sources = []
    for code in sorted({r["source_code"] for r in rows}):
        policy = SourcePolicy.objects.select_for_update().get(pk=code)
        rights = export_rights(policy)
        allowed &= set(rights["fields"])
        sources.append({"code": code, "attribution": rights["attribution"]})
    for row in rows:
        allowed &= set(row["fields"])
    fields = [f for f in FIELD_ORDER if f in allowed]
    if not fields:
        raise PermissionDenied("No common fields are available for export.")
    expires_at = min(
        timezone.now() + timedelta(minutes=10),
        *(datetime.fromisoformat(r["delete_at"]) for r in rows),
    )
    token = signing.dumps(
        {
            "user": str(user.id),
            "workspace": str(workspace_id),
            "job": str(job_id),
            "key": str(uuid4()),
            "ids": sorted(r["id"] for r in rows),
            "fields": fields,
            "expires": expires_at.isoformat(),
        },
        salt=SALT,
    )
    return {
        "kind": "export",
        "workspace_id": str(workspace_id),
        "job_id": str(job_id),
        "confirmation": token,
        "fields": fields,
        "record_count": len(rows),
        "withheld_count": snapshot["withheld_count"],
        "expires_at": expires_at.isoformat(),
        "sources": sources,
        "omitted_fields": [f for f in FIELD_ORDER if f not in allowed],
    }


@method_decorator(never_cache, name="dispatch")
class ExportFormContext(APIView):
    def get(self, request, workspace_id, job_id):
        membership_for(request.user, workspace_id)
        csrf = form_csrf(request)
        if request.query_params:
            raise ValidationError("Export preview query parameters are unavailable.")
        return Response({**export_context(request.user, workspace_id, job_id), "csrf_token": csrf})


def confirmed_selection(user, workspace_id, job_id, token, fields):
    try:
        if type(token) is not str or len(token) > 4096:
            raise ValueError
        data = signing.loads(token, salt=SALT, max_age=600)
        if not isinstance(data, dict) or set(data) != {
            "user",
            "workspace",
            "job",
            "key",
            "ids",
            "fields",
            "expires",
        }:
            raise ValueError
        if (data["user"], data["workspace"], data["job"]) != (
            str(user.id),
            str(workspace_id),
            str(job_id),
        ):
            raise ValueError
        deadline = datetime.fromisoformat(data["expires"])
        if not timezone.is_aware(deadline) or deadline <= timezone.now():
            raise ValueError
        ids, permitted = specification({"result_ids": data["ids"], "fields": data["fields"]})
        _, selected = specification({"result_ids": ids, "fields": fields})
        if not set(selected) <= set(permitted):
            raise ValueError
        key = str(UUID(data["key"]))
    except (signing.BadSignature, ValueError, TypeError, KeyError, AttributeError, APIException):
        raise ValidationError(
            "Export confirmation is invalid or expired. Review a new preview."
        ) from None
    return key, {"result_ids": ids, "fields": selected}


@login_required
@require_POST
@never_cache
def confirmed_export(request, workspace_id, job_id):
    membership_for(request.user, workspace_id)
    if (
        request.GET
        or set(request.POST) - {"csrfmiddlewaretoken", "confirmation", "fields"}
        or len(request.POST.getlist("confirmation")) != 1
        or len(request.POST.getlist("csrfmiddlewaretoken")) != 1
    ):
        return HttpResponseBadRequest("Invalid export confirmation.")
    try:
        key, data = confirmed_selection(
            request.user,
            workspace_id,
            job_id,
            request.POST["confirmation"],
            request.POST.getlist("fields"),
        )
        result = prepare_export(request.user, workspace_id, job_id, key, data)
    except APIException as exc:
        # Plain escaped fallback; no automatic new authority or mutation retry.
        path = f"/workspaces/{workspace_id}/jobs/{job_id}/results"
        review_url = (
            settings.WEB_DASHBOARD_URL.rstrip("/") + path if settings.WEB_DASHBOARD_URL else "/"
        )
        return render(
            request,
            "core/export_unavailable.html",
            {"review_url": review_url},
            status=exc.status_code,
        )
    response = HttpResponse(result.csv_bytes, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="available-results.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Export-Receipt"] = str(result.receipt_id)
    return response
