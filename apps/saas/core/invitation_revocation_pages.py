"""Tenant-scoped pending list and signed, explicit revocation; never reveals bearer codes."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from rest_framework.exceptions import PermissionDenied

from .invitation_pages import private_render
from .invitation_revocation import (
    InvitationStale,
    RevokeInvitationForm,
    review_revoke_token,
    revoke_pending_invitation,
)
from .models import WorkspaceInvitation
from .services import membership_for


@never_cache
@login_required
@require_GET
def pending_invitations_page(request, workspace_id):
    membership = membership_for(request.user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Only owners/admins may inspect pending invitations.")
    if request.GET:
        return HttpResponseBadRequest("Pending invitations do not accept query parameters.")
    pending = (
        WorkspaceInvitation.objects.filter(
            workspace_id=workspace_id,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("target")
        .order_by("created_at", "id")[:10]
    )
    return private_render(
        request,
        "core/invitations_pending.html",
        {"workspace": membership.workspace, "pending": pending, "can_revoke_admin": membership.role == "owner"},
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def revoke_invitation_page(request, workspace_id, invitation_id):
    membership = membership_for(request.user, workspace_id)
    if membership.role not in {"owner", "admin"}:
        return HttpResponseForbidden("Only owners/admins may revoke invitations.")
    invitation = get_object_or_404(
        WorkspaceInvitation, workspace_id=workspace_id, pk=invitation_id
    )
    if membership.role != "owner" and invitation.role == "admin":
        return HttpResponseForbidden("Only owners may revoke administrator invitations.")
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Revocation review does not accept query parameters.")
        if (
            invitation.accepted_at is not None
            or invitation.revoked_at is not None
            or invitation.expires_at <= timezone.now()
        ):
            return private_render(
                request,
                "core/invitation_revoke.html",
                {"workspace": membership.workspace, "invitation": invitation, "form": None, "stale": True},
                status=409,
            )
        form = RevokeInvitationForm(
            actor=request.user,
            workspace_id=workspace_id,
            invitation=invitation,
            initial={
                "confirmation_token": review_revoke_token(
                    request.user, workspace_id, invitation
                ),
            },
        )
        return private_render(
            request,
            "core/invitation_revoke.html",
            {"workspace": membership.workspace, "invitation": invitation, "form": form, "stale": False},
        )
    expected = {"csrfmiddlewaretoken", "confirmation_token", "confirm_revocation"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported revocation fields.")
    form = RevokeInvitationForm(
        request.POST,
        actor=request.user,
        workspace_id=workspace_id,
        invitation=invitation,
    )
    revoked, stale, status = False, False, 400
    if form.is_valid():
        try:
            revoke_pending_invitation(request.user, workspace_id, invitation_id)
        except PermissionDenied:
            return HttpResponseForbidden("Revocation permission is no longer available.")
        except InvitationStale:
            form.add_error(None, "This invitation changed. Open a new review.")
            stale, status = True, 409
        else:
            revoked, status = True, 200
    return private_render(
        request,
        "core/invitation_revoke.html",
        {
            "workspace": membership.workspace,
            "invitation": invitation,
            "form": None if revoked else form,
            "revoked": revoked,
            "stale": stale,
        },
        status=status,
    )
