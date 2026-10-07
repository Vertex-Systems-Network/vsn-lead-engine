"""Private bounded context for native Next forms; Django keeps mutation authority."""

import re

from django.conf import settings
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .cancellation_forms import cancellation_token
from .forms import new_draft_token
from .models import Job, Workspace
from .serializers import JobSerializer
from .services import membership_for


def context_base(request, workspace_id):
    member = membership_for(request.user, workspace_id)
    if member.role not in {"owner", "admin", "member"}:
        raise PermissionDenied("This role cannot change jobs.")
    # Next cannot propagate newly seeded Set-Cookie from a server-component read.
    # A valid existing browser cookie is mandatory; reseed at the account page.
    cookie = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
    if not re.fullmatch(r"[A-Za-z0-9]{32}", cookie):
        raise PermissionDenied("Check your session before opening a form.")
    workspace = Workspace.objects.get(pk=workspace_id)
    return {
        "workspace": {"id": str(workspace.id), "name": workspace.name},
        "csrf_token": get_token(request),
    }


@method_decorator(never_cache, name="dispatch")
class DraftFormContext(APIView):
    def get(self, request, workspace_id):
        data = context_base(request, workspace_id)
        return Response(
            {**data, "kind": "draft", "draft_token": new_draft_token(request.user, workspace_id)}
        )


@method_decorator(never_cache, name="dispatch")
class CancelFormContext(APIView):
    def get(self, request, workspace_id, job_id):
        data = context_base(request, workspace_id)
        job = get_object_or_404(Job, workspace_id=workspace_id, pk=job_id)
        if job.status not in {"draft", "queued"}:
            raise ValidationError("Only draft or queued jobs may be cancelled.")
        return Response(
            {
                **data,
                "kind": "cancel",
                "job": JobSerializer(job).data,
                "confirmation": cancellation_token(request.user, workspace_id, job),
            }
        )
