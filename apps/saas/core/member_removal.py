"""Explicit, short-lived member removal confirmation reusing existing owner-safe service."""

from django import forms
from django.core import signing
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .member_role_forms import latest_audit_id
from .models import Workspace
from .services import change_membership, membership_for

REMOVE_SALT = "saas.member-remove.v1"


class StaleRemoval(Exception):
    """The member or audit history changed after the operator reviewed removal."""


def new_removal_token(actor, workspace_id, target_user_id, current_role):
    return signing.dumps(
        {
            "actor": str(actor.pk),
            "workspace": str(workspace_id),
            "target": str(target_user_id),
            "role": current_role,
            "audit_id": latest_audit_id(workspace_id, target_user_id),
            "purpose": "remove",
        },
        salt=REMOVE_SALT,
    )


class ConfirmMemberRemovalForm(forms.Form):
    confirm_removal = forms.BooleanField(required=True)
    removal_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, workspace_id, target_user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        self.target_user_id = target_user_id

    def clean(self):
        data = super().clean()
        if "confirm_removal" not in data or "removal_token" not in data:
            return data
        try:
            claims = signing.loads(data["removal_token"], salt=REMOVE_SALT, max_age=600)
        except (signing.BadSignature, ValueError, TypeError):
            raise forms.ValidationError("Removal confirmation expired. Open a new form.") from None
        if (
            not isinstance(claims, dict)
            or set(claims) != {"actor", "workspace", "target", "role", "audit_id", "purpose"}
            or claims["purpose"] != "remove"
            or claims["actor"] != str(self.actor.pk)
            or claims["workspace"] != str(self.workspace_id)
            or claims["target"] != str(self.target_user_id)
            or claims["role"] not in {"owner", "admin", "member", "viewer"}
            or (
                claims["audit_id"] is not None
                and (type(claims["audit_id"]) is not int or claims["audit_id"] < 1)
            )
        ):
            raise forms.ValidationError("Removal confirmation is not valid for this member.")
        data["expected_role"] = claims["role"]
        data["expected_audit_id"] = claims["audit_id"]
        return data


@transaction.atomic
def remove_member_confirmed(actor, workspace_id, target_user_id, *, expected_role, expected_audit_id):
    """Serialize and compare the reviewed state before audited member removal."""
    membership_for(actor, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    current_actor = membership_for(actor, workspace_id, lock=True)
    if current_actor.role not in {"owner", "admin"}:
        raise PermissionDenied("Only owners and admins can remove workspace members.")
    target = membership_for(target_user_id, workspace_id, lock=True)
    if (
        target.role != expected_role
        or latest_audit_id(workspace_id, target_user_id) != expected_audit_id
    ):
        raise StaleRemoval()
    change_membership(actor, workspace_id, target_user_id, remove=True)
    return target_user_id
