"""Current-role gated, CSRF-protected member removal review and receipt."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import PermissionDenied, ValidationError

from .member_removal import (
    ConfirmMemberRemovalForm,
    StaleRemoval,
    new_removal_token,
    remove_member_confirmed,
)
from .services import membership_for


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def member_removal_page(request, workspace_id, target_user_id):
    actor_member = membership_for(request.user, workspace_id)
    if actor_member.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Only owners and admins can remove workspace members.")
    target_member = membership_for(target_user_id, workspace_id)
    if actor_member.role != "owner" and target_member.role == "owner":
        return HttpResponseForbidden("Only owners can remove other owners.")
    workspace = actor_member.workspace
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Removal confirmation accepts no query parameters.")
        form = ConfirmMemberRemovalForm(
            actor=request.user,
            workspace_id=workspace_id,
            target_user_id=target_user_id,
            initial={
                "removal_token": new_removal_token(
                    request.user, workspace_id, target_user_id, target_member.role
                ),
            },
        )
        return render(
            request,
            "core/member_removal.html",
            {"workspace": workspace, "target": target_member, "form": form, "removed": False},
        )
    required = {"csrfmiddlewaretoken", "confirm_removal", "removal_token"}
    if set(request.POST) != required or any(
        len(request.POST.getlist(key)) != 1 for key in required
    ):
        return HttpResponseBadRequest("Unsupported removal confirmation fields.")
    form = ConfirmMemberRemovalForm(
        request.POST, actor=request.user, workspace_id=workspace_id, target_user_id=target_user_id
    )
    removed, response_code = False, 400
    if form.is_valid():
        try:
            remove_member_confirmed(
                request.user,
                workspace_id,
                target_user_id,
                expected_role=form.cleaned_data["expected_role"],
                expected_audit_id=form.cleaned_data["expected_audit_id"],
            )
        except StaleRemoval:
            form.add_error(None, "Member state changed. Open a new confirmation before retrying.")
            response_code = 409
        except ValidationError:
            form.add_error(None, "Removal denied by workspace ownership rules.")
        except PermissionDenied:
            return HttpResponseForbidden("Member removal is no longer authorized.")
        else:
            removed, response_code = True, 200
    return render(
        request,
        "core/member_removal.html",
        {
            "workspace": workspace,
            "target": target_member,
            "form": None if removed else form,
            "removed": removed,
        },
        status=response_code,
    )
