"""CSRF-protected manual code exchange; no token in URLs, emails, or JSON APIs."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import PermissionDenied

from .invitations import (
    InvitationUnavailable,
    IssueInvitationForm,
    RedeemInvitationForm,
    invitation_form_token,
    issue_invitation,
    redeem_invitation,
)
from .services import membership_for


def private_render(request, template, context, *, status=200):
    response = render(request, template, context, status=status)
    response["Referrer-Policy"] = "no-referrer"
    return response


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def issue_invitation_page(request, workspace_id):
    actor_member = membership_for(request.user, workspace_id)
    if actor_member.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Workspace invitation requires owner/admin access.")
    if request.method == "GET" and request.GET:
        return HttpResponseBadRequest("Invitation issue form does not accept query parameters.")
    kwargs = {
        "actor": request.user,
        "workspace_id": workspace_id,
        "actor_role": actor_member.role,
    }
    if request.method == "GET":
        form = IssueInvitationForm(
            **kwargs,
            initial={
                "role": "member",
                "confirmation_token": invitation_form_token(request.user, workspace_id),
            },
        )
        return private_render(
            request,
            "core/invitation_issue.html",
            {"workspace": actor_member.workspace, "form": form, "invitation": None},
        )
    expected = {"csrfmiddlewaretoken", "username", "role", "confirmation_token"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported invitation fields.")
    form = IssueInvitationForm(request.POST, **kwargs)
    code, invitation, status = None, None, 400
    if form.is_valid():
        try:
            invitation, code = issue_invitation(
                request.user,
                workspace_id,
                form.cleaned_data["username"],
                form.cleaned_data["role"],
            )
        except PermissionDenied:
            return HttpResponseForbidden("Workspace invitation is no longer authorized.")
        except InvitationUnavailable:
            form.add_error(
                None, "Cannot issue this invitation. Check account and pending invitations."
            )
            status = 409
        else:
            form, status = None, 200
    return private_render(
        request,
        "core/invitation_issue.html",
        {
            "workspace": actor_member.workspace,
            "form": form,
            "invitation": invitation,
            "code": code,
        },
        status=status,
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def redeem_invitation_page(request):
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Never put invitation codes in query strings.")
        return private_render(
            request,
            "core/invitation_redeem.html",
            {"form": RedeemInvitationForm(), "accepted": None},
        )
    expected = {"csrfmiddlewaretoken", "code"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported invitation acceptance fields.")
    form = RedeemInvitationForm(request.POST)
    accepted, status, error = None, 400, None
    if form.is_valid():
        try:
            accepted = redeem_invitation(request.user, form.cleaned_data["code"])
        except InvitationUnavailable:
            error = "Invitation unavailable, expired, already used, or for another account."
        else:
            form, status = None, 200
    if accepted is None:
        # Do not echo a submitted bearer secret into the returned HTML or browser DOM.
        form = RedeemInvitationForm()
        error = error or "Enter a valid private invitation code."
    return private_render(
        request,
        "core/invitation_redeem.html",
        {"form": form, "accepted": accepted, "error": error},
        status=status,
    )
