"""Short-lived actor/plan/revision-bound stop confirmation, never activation."""

from django import forms
from django.core import signing
from rest_framework.exceptions import ValidationError

from .jobs import revision

STOP_TOKEN_SALT = "saas.daily-plan-stop.v1"


def new_stop_token(actor, workspace_id, plan_id, expected_revision):
    return signing.dumps(
        {
            "actor": str(actor.pk),
            "workspace": str(workspace_id),
            "plan": str(plan_id),
            "revision": revision(expected_revision),
        },
        salt=STOP_TOKEN_SALT,
    )


class DailyPlanStopForm(forms.Form):
    stop_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, actor, workspace_id, plan_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.workspace_id = workspace_id
        self.plan_id = plan_id
        self.expected_revision = None

    def clean_stop_token(self):
        value = self.cleaned_data["stop_token"]
        try:
            token = signing.loads(value, salt=STOP_TOKEN_SALT, max_age=3600)
            if not isinstance(token, dict) or set(token) != {
                "actor", "workspace", "plan", "revision"
            }:
                raise ValueError
            if (
                token["actor"] != str(self.actor.pk)
                or token["workspace"] != str(self.workspace_id)
                or token["plan"] != str(self.plan_id)
                or type(token["revision"]) is not int
            ):
                raise ValueError
            self.expected_revision = revision(token["revision"])
        except (signing.BadSignature, ValueError, TypeError, KeyError, AttributeError, ValidationError):
            raise forms.ValidationError(
                "This stop request is invalid or expired. Open a fresh confirmation."
            ) from None
        return value
