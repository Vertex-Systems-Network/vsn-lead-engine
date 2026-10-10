"""Bounded, actor-bound browser form for saving inactive daily plans."""

import uuid

from django import forms
from django.core import signing
from rest_framework.exceptions import ValidationError

from .schedules import validate_clock

PLAN_TOKEN_SALT = "saas.daily-plan.v1"


def new_daily_plan_token(user, workspace_id, job_id):
    return signing.dumps(
        {
            "user": str(user.pk),
            "workspace": str(workspace_id),
            "job": str(job_id),
            "key": str(uuid.uuid4()),
        },
        salt=PLAN_TOKEN_SALT,
    )


class DailyPlanForm(forms.Form):
    timezone = forms.CharField(max_length=64, label="IANA timezone")
    time = forms.TimeField(
        input_formats=["%H:%M"],
        label="Daily local time",
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    plan_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, user, workspace_id, job_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.workspace_id = workspace_id
        self.job_id = job_id
        self.key = None

    def clean_plan_token(self):
        value = self.cleaned_data["plan_token"]
        try:
            token = signing.loads(value, salt=PLAN_TOKEN_SALT, max_age=3600)
            if not isinstance(token, dict) or set(token) != {"user", "workspace", "job", "key"}:
                raise ValueError
            if (
                token["user"] != str(self.user.pk)
                or token["workspace"] != str(self.workspace_id)
                or token["job"] != str(self.job_id)
            ):
                raise ValueError
            self.key = str(uuid.UUID(token["key"]))
        except (signing.BadSignature, ValueError, TypeError, AttributeError, KeyError):
            raise forms.ValidationError(
                "This form is invalid or expired. Open a fresh daily plan form."
            ) from None
        return value

    def clean(self):
        cleaned = super().clean()
        if "timezone" in cleaned and "time" in cleaned:
            try:
                validate_clock(cleaned["timezone"], cleaned["time"])
            except ValidationError as exc:
                raise forms.ValidationError(
                    "Choose a valid IANA timezone and local HH:MM."
                ) from exc
        return cleaned
