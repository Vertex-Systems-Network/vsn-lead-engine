"""Explicit current-owner/admin role change with signed, audit-fenced confirmation.

No automatic invitation, removal, email, provider request or elevation.
All actual changes are made through the existing transactional role service.
"""

from django import forms
from django.core import signing
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .models import MembershipAudit, Workspace
from .services import change_membership, membership_for

SALT = "saas.member-role-change.v1"
ROLES = ("owner", "admin", "member", "viewer")


class StaleMemberRole(Exception):
    """The target role or mutation history changed after confirmation issuance."""


def latest_audit_id(workspace_id, target_user_id):
    return (
        MembershipAudit.objects.filter(workspace_id=workspace_id, target_user_id=target_user_id)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )


def new_role_token(actor, workspace_id, target_user_id, current_role):
    return signing.dumps(
        {
            "actor": str(actor.pk),
            "workspace": str(workspace_id),
            "target": str(target_user_id),
            "role": current_role,
            "audit_id": latest_audit_id(workspace_id, target_user_id),
        },
        salt=SALT,
    )


class MemberRoleChangeForm(forms.Form):
    new_role = forms.ChoiceField(choices=[(role, role.title()) for role in ROLES])
    confirmation_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, actor_role, workspace_id, target_user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        self.target_user_id = target_user_id
        if actor_role != "owner":
            self.fields["new_role"].choices = [
                (role, role.title()) for role in ROLES if role != "owner"
            ]

    def clean(self):
        data = super().clean()
        if "new_role" not in data or "confirmation_token" not in data:
            return data
        try:
            claims = signing.loads(data["confirmation_token"], salt=SALT, max_age=3600)
        except (signing.BadSignature, ValueError, TypeError):
            raise forms.ValidationError(
                "Confirmation expired or invalid. Open a new form."
            ) from None
        if (
            not isinstance(claims, dict)
            or set(claims) != {"actor", "workspace", "target", "role", "audit_id"}
            or claims["actor"] != str(self.actor.pk)
            or claims["workspace"] != str(self.workspace_id)
            or claims["target"] != str(self.target_user_id)
            or claims["role"] not in ROLES
            or (
                claims["audit_id"] is not None
                and (type(claims["audit_id"]) is not int or claims["audit_id"] < 1)
            )
        ):
            raise forms.ValidationError("Confirmation is not valid for this member.")
        if claims["role"] == data["new_role"]:
            raise forms.ValidationError("Select a different role to make a change.")
        data["expected_role"] = claims["role"]
        data["expected_audit_id"] = claims["audit_id"]
        return data


@transaction.atomic
def change_role_confirmed(
    actor, workspace_id, target_user_id, *, expected_role, expected_audit_id, new_role
):
    """Serialize reads, reject stale/A-B-A replays, then use existing authority rules."""
    membership_for(actor, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    current_actor = membership_for(actor, workspace_id, lock=True)
    if current_actor.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners and admins can change member roles.")
    target = membership_for(target_user_id, workspace_id, lock=True)
    if (
        target.role != expected_role
        or latest_audit_id(workspace_id, target_user_id) != expected_audit_id
    ):
        raise StaleMemberRole()
    if new_role == target.role:
        raise StaleMemberRole()
    return change_membership(actor, workspace_id, target_user_id, role=new_role)
