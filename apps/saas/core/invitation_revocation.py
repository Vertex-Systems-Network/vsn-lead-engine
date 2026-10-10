"""Explicit signed, CSRF-gated revocation of a pending one-time invitation."""

from django import forms
from django.core import signing
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import MembershipAudit, Workspace, WorkspaceInvitation
from .services import membership_for

SALT = "saas.invitation-revoke.v1"


class InvitationStale(Exception):
    """Already accepted, revoked, expired, or no longer valid."""


def review_revoke_token(actor, workspace_id, invitation):
    return signing.dumps(
        {
            "actor": str(actor.pk),
            "workspace": str(workspace_id),
            "invitation": str(invitation.pk),
            "target": str(invitation.target_id),
            "role": invitation.role,
            "purpose": "revoke",
        },
        salt=SALT,
    )


class RevokeInvitationForm(forms.Form):
    confirm_revocation = forms.BooleanField(required=True)
    confirmation_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, workspace_id, invitation, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        self.invitation = invitation

    def clean_confirmation_token(self):
        value = self.cleaned_data["confirmation_token"]
        try:
            claim = signing.loads(value, salt=SALT, max_age=600)
        except (signing.BadSignature, ValueError, TypeError):
            raise forms.ValidationError("Review expired. Open a new revocation form.") from None
        if (
            not isinstance(claim, dict)
            or set(claim) != {"actor", "workspace", "invitation", "target", "role", "purpose"}
            or claim["actor"] != str(self.actor.pk)
            or claim["workspace"] != str(self.workspace_id)
            or claim["invitation"] != str(self.invitation.pk)
            or claim["target"] != str(self.invitation.target_id)
            or claim["role"] != self.invitation.role
            or claim["purpose"] != "revoke"
        ):
            raise forms.ValidationError("Confirmation does not match this invitation.")
        return value


@transaction.atomic
def revoke_pending_invitation(actor, workspace_id, invitation_id):
    """Rechecks actor and invitation under the same workspace lock as redemption."""
    membership_for(actor, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    current = membership_for(actor, workspace_id, lock=True)
    if current.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners/admins can revoke invitations.")
    invitation = (
        WorkspaceInvitation.objects.select_for_update()
        .filter(workspace_id=workspace_id, pk=invitation_id)
        .first()
    )
    if invitation is None:
        raise Http404("Invitation not found.")
    if current.role != "owner" and invitation.role == "admin":
        raise PermissionDenied("Only an owner can revoke an administrator invitation.")
    if (
        invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= timezone.now()
    ):
        raise InvitationStale()
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    MembershipAudit.objects.create(
        workspace_id=workspace_id,
        actor=actor,
        target_user_id=invitation.target_id,
        action="invite_revoked",
        previous_role="",
        new_role="",
    )
    return invitation
