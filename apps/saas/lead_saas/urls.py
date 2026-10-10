from core import views
from core.account_forms import sign_in_form, start_sign_in
from core.export_forms import ExportFormContext, confirmed_export
from core.export_history import ExportReceiptList
from core.form_context import (
    CancelFormContext,
    DraftFeedbackContext,
    DraftFormContext,
    SignOutFormContext,
    SubmitFormContext,
)
from core.login_security import ProtectedLoginView
from core.member_role_page import member_role_change_page
from core.password_reset import urlpatterns as password_reset_urls
from core.signup import sign_up_page
from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/export-receipts/",
        ExportReceiptList.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/export-form/",
        ExportFormContext.as_view(),
    ),
    path("workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/export/", confirmed_export),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/exports/",
        views.ResultExportDownload.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/results/",
        views.ResultList.as_view(),
    ),
    path("health/", views.health),
    path("", views.overview),
    path("accounts/start-sign-in/", start_sign_in),
    path("accounts/sign-up/", sign_up_page, name="sign-up-page"),
    path("api/v1/account/sign-in-form/", sign_in_form),
    path("accounts/login/", ProtectedLoginView.as_view()),
    path("accounts/check-session/", views.check_session_page, name="check-session-page"),
    path("api/v1/workspaces/<uuid:workspace_id>/draft-form/", DraftFormContext.as_view()),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/cancel-form/",
        CancelFormContext.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/draft-feedback/<uuid:handle>/",
        DraftFeedbackContext.as_view(),
    ),
    path("api/v1/account/sign-out-form/", SignOutFormContext.as_view()),
    path("accounts/sign-out/", views.sign_out_page, name="sign-out-page"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/v1/workspaces/<uuid:workspace_id>/members/", views.MemberList.as_view()),
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:target_user_id>/role/",
        member_role_change_page,
        name="member-role-change-page",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/member-audit/",
        views.MemberAuditList.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/",
        views.MemberDetail.as_view(),
    ),
    path(
        "workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/daily-plan/",
        views.daily_plan_page,
        name="daily-plan-page",
    ),
    path(
        "workspaces/<uuid:workspace_id>/daily-plans/<uuid:plan_id>/pause/",
        views.pause_daily_plan_page,
        name="pause-daily-plan-page",
    ),
    path(
        "workspaces/<uuid:workspace_id>/schedule-preview/",
        views.daily_time_preview_page,
        name="daily-time-preview-page",
    ),
    path("workspaces/<uuid:workspace_id>/usage/", views.usage_page, name="usage-page"),
    path("api/v1/workspaces/<uuid:workspace_id>/usage/", views.UsageDetail.as_view()),
    path(
        "workspaces/<uuid:workspace_id>/search/new/",
        views.draft_search_page,
        name="draft-search-page",
    ),
    path("workspaces/<uuid:workspace_id>/jobs/", views.job_history_page, name="job-history-page"),
    path(
        "workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/",
        views.job_detail_page,
        name="job-detail-page",
    ),
    path(
        "workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/cancel/",
        views.cancel_pending_page,
        name="cancel-pending-page",
    ),
    path(
        "workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/submit/",
        views.submit_job_page,
        name="submit-job-page",
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/submit-form/",
        SubmitFormContext.as_view(),
    ),
    path(
        "workspaces/<uuid:workspace_id>/sources/",
        views.source_preview_page,
        name="source-preview-page",
    ),
    path("api/v1/workspaces/<uuid:workspace_id>/sources/", views.SourceList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/", views.WorkspaceDetail.as_view()),
    path("api/v1/workspaces/", views.WorkspaceList.as_view()),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/daily-diagnostics/",
        views.DailyPlanDiagnostics.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/daily-plans/",
        views.DailyPlanList.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/daily-plans/<uuid:plan_id>/",
        views.DailyPlanDetail.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/daily-plans/<uuid:plan_id>/readiness/",
        views.DailyPlanReadiness.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/daily-plans/<uuid:plan_id>/occurrences/",
        views.DailyOccurrenceHistory.as_view(),
    ),
    path(
        "api/v1/workspaces/<uuid:workspace_id>/job-summary/",
        views.JobStatusSummary.as_view(),
    ),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/", views.JobList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/", views.JobDetail.as_view()),
] + password_reset_urls
