from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Job, Membership, Workspace
from .serializers import (
    JobSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    SearchSerializer,
    WorkspaceSerializer,
)
from .services import change_membership, create_draft, create_workspace, membership_for


def health(request):
    return JsonResponse({"status": "ok", "service": "vsn-lead-saas", "provider_dispatch": False})


@login_required
def overview(request):
    workspaces = Workspace.objects.filter(membership__user=request.user).order_by("name", "id")
    return render(request, "core/overview.html", {"workspaces": workspaces})


@login_required
@require_GET
@never_cache
def sign_out_page(request):
    return render(request, "core/sign_out.html", {"dashboard_url": settings.LOGIN_REDIRECT_URL})


@login_required
@require_GET
@never_cache
@ensure_csrf_cookie
def check_session_page(request):
    return render(
        request, "core/check_session.html", {"dashboard_url": settings.LOGIN_REDIRECT_URL}
    )


def job_return(workspace_id, job_id):
    if settings.WEB_DASHBOARD_URL:
        return f"{settings.WEB_DASHBOARD_URL}/workspaces/{workspace_id}/jobs/{job_id}"
    return reverse("job-detail-page", args=[workspace_id, job_id])


class WorkspaceList(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(membership__user=self.request.user).order_by("name", "id")

    def perform_create(self, serializer):
        serializer.instance = create_workspace(self.request.user, serializer.validated_data)


class JobList(APIView):
    def get(self, request, workspace_id):
        membership_for(request.user, workspace_id)
        # Bounded cursor continuation; filter tenant before applying the cursor.
        query = Job.objects.filter(workspace_id=workspace_id).order_by("id")
        after = request.query_params.get("after")
        if after:
            from uuid import UUID

            from rest_framework.exceptions import ValidationError

            try:
                query = query.filter(id__gt=UUID(after))
            except ValueError:
                raise ValidationError({"after": "Invalid continuation cursor."}) from None
        rows = list(query[:26])
        return Response(
            {
                "results": JobSerializer(rows[:25], many=True).data,
                "next": str(rows[24].id) if len(rows) > 25 else None,
            }
        )

    def post(self, request, workspace_id):
        membership_for(request.user, workspace_id)
        serializer = SearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job, created = create_draft(
            request.user,
            workspace_id,
            serializer.validated_data,
            request.headers.get("Idempotency-Key"),
        )
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class JobDetail(APIView):
    def get(self, request, workspace_id, job_id):
        membership_for(request.user, workspace_id)
        job = get_object_or_404(Job, workspace_id=workspace_id, id=job_id)
        return Response(JobSerializer(job).data)


class MemberList(generics.ListAPIView):
    serializer_class = MembershipSerializer

    def get_queryset(self):
        from rest_framework.exceptions import PermissionDenied

        membership = membership_for(self.request.user, self.kwargs["workspace_id"])
        if membership.role not in {"owner", "admin"}:
            raise PermissionDenied("This role cannot manage members.")
        return Membership.objects.filter(workspace_id=self.kwargs["workspace_id"]).order_by(
            "user_id"
        )


class MemberDetail(APIView):
    def patch(self, request, workspace_id, user_id):
        membership_for(request.user, workspace_id)
        serializer = MembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = change_membership(
            request.user, workspace_id, user_id, role=serializer.validated_data["role"]
        )
        return Response(MembershipSerializer(member).data)

    def delete(self, request, workspace_id, user_id):
        change_membership(request.user, workspace_id, user_id, remove=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsageDetail(APIView):
    def get(self, request, workspace_id):
        from .usage_snapshot import usage_snapshot

        return Response(usage_snapshot(request.user, workspace_id))


@login_required
@require_GET
def usage_page(request, workspace_id):
    from .usage_snapshot import usage_snapshot

    snapshot = usage_snapshot(request.user, workspace_id)
    workspace = Workspace.objects.get(pk=workspace_id)
    return render(request, "core/usage.html", {"workspace": workspace, "usage": snapshot})


@login_required
@require_GET
def job_history_page(request, workspace_id):
    from .job_history import InvalidHistoryCursor, history_snapshot

    try:
        workspace, jobs, next_cursor = history_snapshot(
            request.user, workspace_id, request.GET.get("after")
        )
    except InvalidHistoryCursor:
        return HttpResponseBadRequest("Invalid or expired job history continuation.")
    return render(
        request,
        "core/jobs.html",
        {
            "workspace": workspace,
            "jobs": jobs,
            "next_cursor": next_cursor,
            "can_save_draft": membership_for(request.user, workspace_id).role
            in {"owner", "admin", "member"},
        },
    )


@login_required
@require_GET
def job_detail_page(request, workspace_id, job_id):
    from .job_history import detail_snapshot

    workspace, job = detail_snapshot(request.user, workspace_id, job_id)
    return render(
        request,
        "core/job_detail.html",
        {
            "workspace": workspace,
            "job": job,
            "can_cancel_pending": job.status in {"draft", "queued"}
            and membership_for(request.user, workspace_id).role in {"owner", "admin", "member"},
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def draft_search_page(request, workspace_id):
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from .forms import DraftSearchForm, new_draft_token
    from .services import IdempotencyConflict

    member = membership_for(request.user, workspace_id)
    if member.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("This role cannot save search drafts.")
    workspace = Workspace.objects.get(pk=workspace_id)
    if request.method == "GET":
        form = DraftSearchForm(
            user=request.user,
            workspace_id=workspace_id,
            initial={"draft_token": new_draft_token(request.user, workspace_id)},
        )
        response_status = 200
    else:
        form = DraftSearchForm(request.POST, user=request.user, workspace_id=workspace_id)
        response_status = 400
        if form.is_valid():
            try:
                job, _ = create_draft(request.user, workspace_id, form.search, form.key)
            except PermissionDenied:
                return HttpResponseForbidden("This role cannot save search drafts.")
            except IdempotencyConflict:
                form.add_error(
                    None, "This form already saved a different search. Open a new draft form."
                )
                response_status = 409
            except ValidationError:
                form.add_error(
                    None, "The draft could not be saved. Open a new draft form and try again."
                )
            else:
                return HttpResponseRedirect(job_return(workspace_id, job.id), status=303)
    return render(
        request,
        "core/draft_search.html",
        {"workspace": workspace, "form": form},
        status=response_status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def cancel_pending_page(request, workspace_id, job_id):
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from .cancellation_forms import PendingCancellationForm, cancellation_token
    from .job_history import detail_snapshot
    from .jobs import RevisionConflict, cancel_pending_job

    member = membership_for(request.user, workspace_id)
    if member.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("This role cannot cancel pending jobs.")
    workspace, job = detail_snapshot(request.user, workspace_id, job_id)
    kwargs = {"user": request.user, "workspace_id": workspace_id, "job_id": job_id}
    if request.method == "GET":
        if job.status not in {"draft", "queued"}:
            return HttpResponseBadRequest("Only draft or queued jobs can be cancelled.", status=409)
        form = PendingCancellationForm(
            initial={"confirmation": cancellation_token(request.user, workspace_id, job)}, **kwargs
        )
        response_status = 200
    else:
        form = PendingCancellationForm(request.POST, **kwargs)
        response_status = 400
        if form.is_valid():
            try:
                cancel_pending_job(request.user, workspace_id, job_id, form.expected_revision)
            except PermissionDenied:
                return HttpResponseForbidden("This role cannot cancel pending jobs.")
            except RevisionConflict:
                form.add_error(None, "The job changed. Review its details before cancelling again.")
                response_status = 409
            except ValidationError:
                form.add_error(None, "Cancellation is unavailable. Review the job again.")
            else:
                return HttpResponseRedirect(job_return(workspace_id, job_id), status=303)
    return render(
        request,
        "core/cancel_pending.html",
        {"workspace": workspace, "job": job, "form": form},
        status=response_status,
    )


@login_required
@require_GET
def source_preview_page(request, workspace_id):
    from .source_preview import source_preview

    workspace, entries, truncated = source_preview(request.user, workspace_id)
    return render(
        request,
        "core/source_preview.html",
        {"workspace": workspace, "sources": entries, "truncated": truncated},
    )
