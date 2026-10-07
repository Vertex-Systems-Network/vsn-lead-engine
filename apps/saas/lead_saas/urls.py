from django.contrib.auth import views as auth_views
from django.urls import path
from core import views

urlpatterns = [
    path("health/", views.health),
    path("", views.overview),
    path("accounts/login/", auth_views.LoginView.as_view()),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/v1/workspaces/<uuid:workspace_id>/members/", views.MemberList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/members/<uuid:user_id>/", views.MemberDetail.as_view()),
    path("api/v1/workspaces/", views.WorkspaceList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/", views.JobList.as_view()),
    path("api/v1/workspaces/<uuid:workspace_id>/jobs/<uuid:job_id>/", views.JobDetail.as_view()),
]
