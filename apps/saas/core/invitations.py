"""Bounded, manually shared invitations for *existing* signed-in SaaS accounts.

This is not an email system, user lookup API, or public sign-up shortcut.
The 256-bit random redemption code is shown once and never persisted in plaintext.
"""

import hashlib
import secrets
from datetime import timedelta

from django import forms
from django.core import signing
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import Membership, MembershipAudit, User, Workspace, WorkspaceInvitation
from .services import membership_for

INVITE_FORM_SALT = "saas.issue-invitation.v1"
INVITABLE_ROLES = ("admin", "member", "viewer")
MAX_PENDING_PER_WORKSPACE = 10
INVITATION_LIFETIME = timedelta(hours=24)


class InvitationUnavailable(Exception):
    """Generic failure to avoid disclosing account identity or other workspace data."""


def invitation_form_token(actor, workspace_id):
    return signing.dumps(
        {"actor": str(actor.pk), "workspace": str(workspace_id), "nonce": secrets.token_hex(16)},
        salt=INVITE_FORM_SALT,
    )


class IssueInvitationForm(forms.Form):
    username = forms.CharField(max_length=150, strip=True)
    role = forms.ChoiceField(choices=[(role, role.title()) for role in INVITABLE_ROLES])
    confirmation_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, workspace_id, actor_role, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        if actor_role != "owner":
            self.fields["role"].choices = [
                (role, role.title()) for role in INVITABLE_ROLES if role != "admin"
            ]

    def clean_confirmation_token(self):
        value = self.cleaned_data["confirmation_token"]
        try:
            claim = signing.loads(value, salt=INVITE_FORM_SALT, max_age=600)
        except (signing.BadSignature, TypeError, ValueError):
            raise forms.ValidationError("Review expired. Open a new invitation form.") from None
        if (
            not isinstance(claim, dict)
            or set(claim) != {"actor", "workspace", "nonce"}
            or claim["actor"] != str(self.actor.pk)
            or claim["workspace"] != str(self.workspace_id)
            or not isinstance(claim["nonce"], str)
            or len(claim["nonce"]) != 32
        ):
            raise forms.ValidationError("Invitation review context does not match this account.")
        return value


class RedeemInvitationForm(forms.Form):
    code = forms.CharField(min_length=40, max_length=128, strip=True)


@transaction.atomic
def issue_invitation(actor, workspace_id, username, role):
    if role not in INVITABLE_ROLES:
        raise InvitationUnavailable()
    membership_for(actor, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    current = membership_for(actor, workspace_id, lock=True)
    if current.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners and administrators may invite existing users.")
    if role == "admin" and current.role != "owner":
        raise PermissionDenied("Only owners can invite administrators.")
    target = User.objects.filter(username=username, is_active=True).first()
    if target is None or Membership.objects.filter(workspace_id=workspace_id, user=target).exists():
        raise InvitationUnavailable()
    pending = WorkspaceInvitation.objects.filter(
        workspace_id=workspace_id,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if pending.count() >= MAX_PENDING_PER_WORKSPACE or pending.filter(target=target).exists():
        raise InvitationUnavailable()
    code = secrets.token_urlsafe(32)
    invitation = WorkspaceInvitation.objects.create(
        workspace_id=workspace_id,
        target=target,
        created_by=actor,
        role=role,
        token_hash=hashlib.sha256(code.encode("ascii")).hexdigest(),
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    return invitation, code


@transaction.atomic
def redeem_invitation(actor, code):
    if not actor.is_active or not isinstance(code, str) or not (40 <= len(code) <= 128):
        raise InvitationUnavailable()
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    invitation = WorkspaceInvitation.objects.filter(token_hash=digest).first()
    if invitation is None:
        raise InvitationUnavailable()
    Workspace.objects.select_for_update().get(pk=invitation.workspace_id)
    invitation = WorkspaceInvitation.objects.select_for_update().get(pk=invitation.pk)
    if (
        invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= timezone.now()
        or invitation.target_id != actor.pk
        or invitation.role not in INVITABLE_ROLES
        or Membership.objects.filter(workspace_id=invitation.workspace_id, user=actor).exists()
    ):
        raise InvitationUnavailable()
    try:
        issuer = membership_for(invitation.created_by, invitation.workspace_id, lock=True)
    except Http404:
        raise InvitationUnavailable() from None
    if issuer.role not in {"owner", "admin"} or (
        invitation.role == "admin" and issuer.role != "owner"
    ):
        raise InvitationUnavailable()
    Membership.objects.create(
        workspace_id=invitation.workspace_id, user=actor, role=invitation.role
    )
    MembershipAudit.objects.create(
        workspace_id=invitation.workspace_id,
        actor=actor,
        target_user_id=actor.pk,
        action="invite_accepted",
        previous_role="",
        new_role=invitation.role,
    )
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    return invitation
