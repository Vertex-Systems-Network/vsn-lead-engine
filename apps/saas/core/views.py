from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
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


@method_decorator(never_cache, name="dispatch")
class ResultExportDownload(APIView):
    def post(self, request, workspace_id, job_id):
        from rest_framework.exceptions import ValidationError

        from .result_exports import prepare_export

        membership_for(request.user, workspace_id)
        if request.query_params:
            raise ValidationError("Export query parameters are unavailable.")
        result = prepare_export(
            request.user, workspace_id, job_id, request.headers.get("Idempotency-Key"), request.data
        )
        response = HttpResponse(result.csv_bytes, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="available-results.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Export-Receipt"] = str(result.receipt_id)
        return response


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


@method_decorator(never_cache, name="dispatch")
class WorkspaceDetail(APIView):
    """Read-only exact workspace identity under current membership authority."""

    def get(self, request, workspace_id):
        membership = membership_for(request.user, workspace_id)
        return Response(WorkspaceSerializer(membership.workspace).data)


@method_decorator(never_cache, name="dispatch")
class DailyPlanDetail(APIView):
    """Current-member plan snapshot for review, with no mutation or scheduler."""

    def get(self, request, workspace_id, plan_id):
        from rest_framework.exceptions import ValidationError

        from .models import DailySchedule

        membership_for(request.user, workspace_id)
        if request.query_params:
            raise ValidationError("Daily plan detail does not accept query parameters.")
        plan = get_object_or_404(DailySchedule, pk=plan_id, workspace_id=workspace_id)
        serializer = SearchSerializer(data=plan.search)
        if not serializer.is_valid():
            raise ValidationError("Stored daily plan configuration requires reconciliation.")
        return Response(
            {
                "id": str(plan.id),
                "workspace_id": str(workspace_id),
                "timezone": plan.timezone,
                "local_time": plan.local_time.strftime("%H:%M"),
                "enabled": plan.enabled,
                "revision": plan.revision,
                "created_at": plan.created_at.isoformat(),
                "search": serializer.validated_data,
            }
        )


@method_decorator(never_cache, name="dispatch")
class DailyPlanDiagnostics(APIView):
    """Owner/admin-only, no-store and explicitly non-mutating due-candidate view."""

    def get(self, request, workspace_id):
        from rest_framework.exceptions import ValidationError

        from .daily_due_diagnostics import due_plan_diagnostics

        if set(request.query_params) - {"after"} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise ValidationError("Unsupported or repeated diagnostics parameter.")
        return Response(
            due_plan_diagnostics(
                request.user,
                workspace_id,
                after=request.query_params.get("after"),
            )
        )


@method_decorator(never_cache, name="dispatch")
class DailyPlanList(APIView):
    """Read-only list; all membership and cursor checks run on the Django side."""

    def get(self, request, workspace_id):
        from .daily_plan_query import daily_plans_page

        return Response(daily_plans_page(request.user, workspace_id, request.query_params))


@method_decorator(never_cache, name="dispatch")
class JobStatusSummary(APIView):
    """All-state totals for a single currently authorized workspace."""

    def get(self, request, workspace_id):
        from rest_framework.exceptions import ValidationError

        from .job_status_summary import job_status_snapshot

        if request.query_params:
            raise ValidationError("Job summary does not accept query parameters.")
        return Response(job_status_snapshot(request.user, workspace_id))


@method_decorator(never_cache, name="dispatch")
class JobList(APIView):
    def get(self, request, workspace_id):
        membership_for(request.user, workspace_id)
        from .job_query import job_page

        rows, next_cursor = job_page(workspace_id, request.query_params)
        return Response({"results": JobSerializer(rows, many=True).data, "next": next_cursor})

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


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def pause_daily_plan_page(request, workspace_id, plan_id):
    """Owner/admin explicit CSRF confirmation; can only disable future planning."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from .daily_plan_pause import PauseDailyPlanForm, issue_pause_token, pause_daily_schedule
    from .jobs import RevisionConflict
    from .models import DailySchedule

    membership = membership_for(request.user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Only workspace owners and admins can pause plans.")
    workspace = membership.workspace
    plan = get_object_or_404(DailySchedule, pk=plan_id, workspace_id=workspace_id)
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Pause confirmation does not accept query parameters.")
        form = (
            PauseDailyPlanForm(
                actor=request.user,
                workspace_id=workspace_id,
                plan_id=plan_id,
                initial={
                    "expected_revision": plan.revision,
                    "pause_token": issue_pause_token(
                        request.user, workspace_id, plan_id, plan.revision
                    ),
                },
            )
            if plan.enabled
            else None
        )
        return render(
            request,
            "core/daily_plan_pause.html",
            {"workspace": workspace, "plan": plan, "form": form, "receipt": False},
        )
    fields = {"csrfmiddlewaretoken", "expected_revision", "pause_token"}
    if set(request.POST) != fields or any(
        len(request.POST.getlist(key)) != 1 for key in request.POST
    ):
        return HttpResponseBadRequest("Unsupported pause confirmation fields.")
    form = PauseDailyPlanForm(
        request.POST, actor=request.user, workspace_id=workspace_id, plan_id=plan_id
    )
    status_code, receipt = 400, False
    if form.is_valid():
        try:
            plan, changed = pause_daily_schedule(
                request.user, workspace_id, plan_id, form.cleaned_data["expected_revision"]
            )
        except RevisionConflict:
            form.add_error(None, "Plan changed. Refresh the form before retrying.")
            status_code = 409
        except ValidationError:
            form.add_error(None, "Plan revision is not valid.")
        except PermissionDenied:
            return HttpResponseForbidden("Plan pause permission is no longer available.")
        else:
            status_code, receipt = 200, True
            # A replay with an unchanged, already-disabled revision is a no-op.
            plan.refresh_from_db()
    return render(
        request,
        "core/daily_plan_pause.html",
        {"workspace": workspace, "plan": plan, "form": form, "receipt": receipt},
        status=status_code,
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def daily_plan_page(request, workspace_id, job_id):
    """Create only an inactive schedule plan from the saved draft's server-side scope."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from .daily_plan_forms import DailyPlanForm, new_daily_plan_token
    from .schedules import create_daily_schedule
    from .services import IdempotencyConflict

    membership = membership_for(request.user, workspace_id)
    if membership.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("This role cannot save daily plans.")
    workspace = membership.workspace
    job = get_object_or_404(Job, pk=job_id, workspace_id=workspace_id, status="draft")
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Daily plan form does not accept query parameters.")
        form = DailyPlanForm(
            user=request.user,
            workspace_id=workspace_id,
            job_id=job_id,
            initial={
                "timezone": workspace.timezone,
                "time": "08:00",
                "plan_token": new_daily_plan_token(request.user, workspace_id, job_id),
            },
        )
        return render(
            request,
            "core/daily_plan.html",
            {"workspace": workspace, "job": job, "form": form, "plan": None},
        )
    expected = {"csrfmiddlewaretoken", "timezone", "time", "plan_token"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in request.POST
    ):
        return HttpResponseBadRequest("Unsupported daily plan form fields.")
    form = DailyPlanForm(request.POST, user=request.user, workspace_id=workspace_id, job_id=job_id)
    plan = None
    response_status = 400
    if form.is_valid():
        try:
            plan, created = create_daily_schedule(
                request.user,
                workspace_id,
                job.search,
                form.cleaned_data["timezone"],
                form.cleaned_data["time"],
                form.key,
            )
        except IdempotencyConflict:
            form.add_error(None, "This plan key was already used for different settings.")
            response_status = 409
        except ValidationError:
            form.add_error(None, "The saved search needs fresh validation before scheduling.")
        except PermissionDenied:
            return HttpResponseForbidden("Daily plan permission is no longer available.")
        else:
            response_status = 201 if created else 200
    return render(
        request,
        "core/daily_plan.html",
        {"workspace": workspace, "job": job, "form": form, "plan": plan},
        status=response_status,
    )


@never_cache
@login_required
@require_GET
def daily_time_preview_page(request, workspace_id):
    """Member-only GET preview; no schedule, queued job or provider side effect."""
    from .schedule_preview import DailyTimePreviewForm, upcoming_daily_preview

    member = membership_for(request.user, workspace_id)
    workspace = member.workspace
    values = request.GET
    supplied = bool(values)
    if supplied and (
        set(values) != {"timezone", "time"} or any(len(values.getlist(key)) != 1 for key in values)
    ):
        return HttpResponseBadRequest("Supply only one timezone and one local time.")
    form = DailyTimePreviewForm(
        values if supplied else {"timezone": workspace.timezone, "time": "08:00"}
    )
    decisions = (
        upcoming_daily_preview(form.cleaned_data["timezone"], form.cleaned_data["time"])
        if form.is_valid()
        else []
    )
    return render(
        request,
        "core/daily_time_preview.html",
        {"workspace": workspace, "form": form, "decisions": decisions},
        status=200 if form.is_valid() else 400,
    )


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
            "can_submit": job.status == "draft"
            and membership_for(request.user, workspace_id).role in {"owner", "admin", "member"},
        },
    )


@never_cache
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
    if request.method == "POST" and settings.WEB_DASHBOARD_URL:
        from .draft_feedback import save_feedback

        handle = save_feedback(request, workspace_id, form, response_status)
        if handle:
            return HttpResponseRedirect(
                f"{settings.WEB_DASHBOARD_URL}/workspaces/{workspace_id}/search/new?feedback={handle}",
                status=303,
            )
    return render(
        request,
        "core/draft_search.html",
        {"workspace": workspace, "form": form},
        status=response_status,
    )


@never_cache
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
        notice = "invalid"
        if form.is_valid():
            try:
                cancel_pending_job(request.user, workspace_id, job_id, form.expected_revision)
            except PermissionDenied:
                return HttpResponseForbidden("This role cannot cancel pending jobs.")
            except RevisionConflict:
                form.add_error(None, "The job changed. Review its details before cancelling again.")
                response_status = 409
                notice = "changed"
            except ValidationError:
                form.add_error(None, "Cancellation is unavailable. Review the job again.")
                notice = "unavailable"
            else:
                return HttpResponseRedirect(job_return(workspace_id, job_id), status=303)
    if request.method == "POST" and settings.WEB_DASHBOARD_URL:
        return HttpResponseRedirect(
            f"{job_return(workspace_id, job_id)}/cancel?notice={notice}", status=303
        )
    return render(
        request,
        "core/cancel_pending.html",
        {"workspace": workspace, "job": job, "form": form},
        status=response_status,
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def submit_job_page(request, workspace_id, job_id):
    """Customer submit: reserve usage and queue a draft for fulfilment."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from .cancellation_forms import JobSubmissionForm, submission_token
    from .job_history import detail_snapshot
    from .jobs import RevisionConflict, enqueue_job

    member = membership_for(request.user, workspace_id)
    if member.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("This role cannot submit jobs.")
    workspace, job = detail_snapshot(request.user, workspace_id, job_id)
    kwargs = {"user": request.user, "workspace_id": workspace_id, "job_id": job_id}
    if request.method == "GET":
        if job.status != "draft":
            return HttpResponseBadRequest("Only draft jobs can be submitted.", status=409)
        form = JobSubmissionForm(
            initial={"confirmation": submission_token(request.user, workspace_id, job)}, **kwargs
        )
        response_status = 200
    else:
        form = JobSubmissionForm(request.POST, **kwargs)
        response_status = 400
        notice = "invalid"
        if form.is_valid():
            try:
                enqueue_job(request.user, workspace_id, job_id, form.expected_revision)
            except PermissionDenied:
                # Inactive plan, exhausted limits or a source that cannot serve this search.
                form.add_error(None, "This workspace cannot run this search right now.")
                response_status = 403
                notice = "limits"
            except RevisionConflict:
                form.add_error(None, "The job changed. Review its details before submitting.")
                response_status = 409
                notice = "changed"
            except ValidationError:
                form.add_error(None, "Submission is unavailable. Review the job again.")
                notice = "unavailable"
            else:
                return HttpResponseRedirect(job_return(workspace_id, job_id), status=303)
    if request.method == "POST" and settings.WEB_DASHBOARD_URL:
        return HttpResponseRedirect(
            f"{job_return(workspace_id, job_id)}/submit?notice={notice}", status=303
        )
    return render(
        request,
        "core/submit_job.html",
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


@method_decorator(never_cache, name="dispatch")
class SourceList(APIView):
    def get(self, request, workspace_id):

        from .source_preview import source_api_snapshot

        return Response(source_api_snapshot(request.user, workspace_id))


@method_decorator(never_cache, name="dispatch")
class ResultList(APIView):
    def get(self, request, workspace_id, job_id):
        from .result_query import result_filters, results_snapshot

        # Current v2 intake is one complete batch <=25 per job; no unbounded reads.
        membership_for(request.user, workspace_id)
        filters = result_filters(request.query_params)
        return Response(results_snapshot(request.user, workspace_id, job_id, **filters))
