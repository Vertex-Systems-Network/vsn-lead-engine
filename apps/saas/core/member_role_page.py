"""Server-rendered, CSRF-protected role change; no background member mutations."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import PermissionDenied, ValidationError

from .member_role_forms import (
    MemberRoleChangeForm,
    StaleMemberRole,
    change_role_confirmed,
    new_role_token,
)
from .services import membership_for


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def member_role_change_page(request, workspace_id, target_user_id):
    actor_member = membership_for(request.user, workspace_id)
    if actor_member.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Only workspace owners and admins can change roles.")
    target_member = membership_for(target_user_id, workspace_id)
    if actor_member.role != "owner" and target_member.role == "owner":
        return HttpResponseForbidden("Only an owner can change ownership.")
    workspace = actor_member.workspace
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Role change form does not accept query parameters.")
        form = MemberRoleChangeForm(
            actor=request.user,
            actor_role=actor_member.role,
            workspace_id=workspace_id,
            target_user_id=target_user_id,
            initial={
                "new_role": target_member.role,
                "confirmation_token": new_role_token(
                    request.user, workspace_id, target_user_id, target_member.role
                ),
            },
        )
        return render(
            request,
            "core/member_role_change.html",
            {"workspace": workspace, "target": target_member, "form": form, "changed": False},
        )
    expected = {"csrfmiddlewaretoken", "new_role", "confirmation_token"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported member confirmation fields.")
    form = MemberRoleChangeForm(
        request.POST,
        actor=request.user,
        actor_role=actor_member.role,
        workspace_id=workspace_id,
        target_user_id=target_user_id,
    )
    response_code, changed = 400, False
    if form.is_valid():
        try:
            target_member = change_role_confirmed(
                request.user,
                workspace_id,
                target_user_id,
                expected_role=form.cleaned_data["expected_role"],
                expected_audit_id=form.cleaned_data["expected_audit_id"],
                new_role=form.cleaned_data["new_role"],
            )
        except StaleMemberRole:
            form.add_error(None, "Member state changed. Open a new confirmation before retrying.")
            response_code = 409
        except ValidationError:
            form.add_error(None, "Role change denied by workspace ownership rules.")
        except PermissionDenied:
            return HttpResponseForbidden("Role change permission is no longer available.")
        else:
            response_code, changed = 200, True
    return render(
        request,
        "core/member_role_change.html",
        {
            "workspace": workspace,
            "target": target_member,
            "form": None if changed else form,
            "changed": changed,
        },
        status=response_code,
    )
