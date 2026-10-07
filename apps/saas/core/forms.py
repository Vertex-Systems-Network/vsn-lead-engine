"""Draft-only search form; the API serializer stays the normalized contract."""

import uuid

from django import forms
from django.core import signing
from rest_framework.exceptions import ValidationError

from .serializers import SearchSerializer

TOKEN_SALT = "saas.draft-form.v1"


def new_draft_token(user, workspace_id):
    return signing.dumps(
        {"user": str(user.pk), "workspace": str(workspace_id), "key": str(uuid.uuid4())},
        salt=TOKEN_SALT,
    )


class DraftSearchForm(forms.Form):
    countries = forms.MultipleChoiceField(
        choices=[("US", "United States"), ("CA", "Canada")],
        widget=forms.CheckboxSelectMultiple,
        initial=["US"],
    )
    categories = forms.CharField(
        max_length=1600,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One category per line, up to 12. These are requested preferences, not verified source coverage.",
    )
    statuses = forms.MultipleChoiceField(
        choices=[("active", "Active"), ("closed", "Closed"), ("opening_soon", "Opening soon")],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Optional requested business statuses; source support is unverified.",
    )
    required_fields = forms.MultipleChoiceField(
        choices=[
            ("phone", "Phone"),
            ("name", "Name"),
            ("website", "Website"),
            ("address", "Address"),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        initial=["phone"],
        help_text="Phone qualification is always required, even if not selected.",
    )
    source_codes = forms.CharField(
        required=False,
        max_length=900,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional requested source codes, one per line, up to 12. No source is activated by saving.",
    )
    result_limit = forms.IntegerField(min_value=1, max_value=1000, initial=100)
    draft_token = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, user, workspace_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.workspace_id = workspace_id
        self.search = None
        self.key = None

    def clean_draft_token(self):
        value = self.cleaned_data["draft_token"]
        try:
            token = signing.loads(value, salt=TOKEN_SALT, max_age=86400)
            if not isinstance(token, dict) or set(token) != {"user", "workspace", "key"}:
                raise ValueError
            if token["user"] != str(self.user.pk) or token["workspace"] != str(self.workspace_id):
                raise ValueError
            self.key = str(uuid.UUID(token["key"]))
        except (signing.BadSignature, ValueError, TypeError, AttributeError):
            raise forms.ValidationError(
                "This draft form is invalid or expired. Open a new draft form and try again."
            ) from None
        return value

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        data = {key: value for key, value in cleaned.items() if key != "draft_token"}
        for key in ("categories", "source_codes"):
            data[key] = [line.strip() for line in data[key].splitlines() if line.strip()]
        serializer = SearchSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            for key, errors in exc.detail.items():
                # Serializer nested item errors must be reduced to plain messages,
                # not embedded HTML or provider/client-authoritative instructions.
                if isinstance(errors, dict):
                    errors = [message for messages in errors.values() for message in messages]
                self.add_error(key if key in self.fields else None, [str(e) for e in errors])
        else:
            self.search = serializer.validated_data
        return cleaned
