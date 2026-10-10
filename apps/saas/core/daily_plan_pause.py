"""Fail-closed, actor-bound pause-only daily plan control.

This module can only turn an already enabled plan OFF. It does not enable,
delete, materialize, enqueue, cancel previous jobs, or contact providers.
"""

from django import forms
from django.core import signing
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import RevisionConflict, revision
from .models import DailySchedule
from .services import membership_for
from .usage import lock_workspace

PAUSE_SALT = "saas.daily-plan.pause.v1"


def issue_pause_token(actor, workspace_id, plan_id, expected_revision):
    return signing.dumps(
        {
            "actor": str(actor.pk),
            "workspace": str(workspace_id),
            "plan": str(plan_id),
            "revision": revision(expected_revision),
        },
        salt=PAUSE_SALT,
    )


class PauseDailyPlanForm(forms.Form):
    expected_revision = forms.IntegerField(min_value=1, max_value=2147483646)
    pause_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, workspace_id, plan_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        self.plan_id = plan_id

    def clean(self):
        data = super().clean()
        if "pause_token" not in data or "expected_revision" not in data:
            return data
        try:
            claims = signing.loads(data["pause_token"], salt=PAUSE_SALT, max_age=3600)
        except (signing.BadSignature, ValueError, TypeError):
            raise forms.ValidationError("Pause confirmation expired. Open a new form.") from None
        if (
            not isinstance(claims, dict)
            or set(claims) != {"actor", "workspace", "plan", "revision"}
            or claims["actor"] != str(self.actor.pk)
            or claims["workspace"] != str(self.workspace_id)
            or claims["plan"] != str(self.plan_id)
            or type(claims["revision"]) is not int
            or claims["revision"] != data["expected_revision"]
        ):
            raise forms.ValidationError("Pause confirmation is not valid for this plan.")
        return data


@transaction.atomic
def pause_daily_schedule(actor, workspace_id, plan_id, expected_revision):
    """Atomic workspace-serialized pause; stale forms cannot overwrite revision."""
    expected_revision = revision(expected_revision)
    lock_workspace(actor, workspace_id)
    if membership_for(actor, workspace_id, lock=True).role not in {"owner", "admin"}:
        raise PermissionDenied("Only workspace owners and admins can pause daily plans.")
    plan = (
        DailySchedule.objects.select_for_update()
        .filter(pk=plan_id, workspace_id=workspace_id)
        .first()
    )
    if plan is None:
        raise Http404("Workspace resource not found.")
    if plan.revision != expected_revision:
        raise RevisionConflict()
    if not plan.enabled:
        return plan, False
    if plan.revision >= 2147483646:
        raise ValidationError("Plan revision limit reached.")
    plan.enabled = False
    plan.revision += 1
    plan.save(update_fields=["enabled", "revision"])
    return plan, True
