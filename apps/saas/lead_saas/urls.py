from core import views
from core.account_forms import sign_in_form, start_sign_in
from core.export_forms import ExportFormContext, confirmed_export
from core.form_context import (
    CancelFormContext,
    DraftFeedbackContext,
    DraftFormContext,
    SignOutFormContext,
)
from core.login_security import ProtectedLoginView
from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
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
        "api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/",
        views.MemberDetail.as_view(),
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
        "workspaces/<uuid:workspace_id>/sources/",
        views.source_preview_page,
        name="source-preview-page",
    ),
    path("api/v1/workspaces/<uuid:workspace_id>/sources/", views.SourceList.as_view()),
    path("api/v1/workspaces/", views.WorkspaceList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/", views.JobList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/", views.JobDetail.as_view()),
]
