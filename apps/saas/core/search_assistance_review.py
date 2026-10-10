"""Short-lived, actor/tenant-bound no-model search suggestion review handoff.

Only a normalized *proposed* search is signed. Raw user intent is never
retained; acceptance creates only an editable form, not a job/usage reservation.
"""

from django import forms
from django.core import signing

from .forms import DraftSearchForm, new_draft_token
from .search_assistance import CATEGORY_PATTERNS
from .serializers import SearchSerializer

REVIEW_SALT = "saas.local-assist-review.v1"
ALLOWED_CATEGORIES = {name for name, _ in CATEGORY_PATTERNS}
REVIEW_MAX_AGE_SECONDS = 600
REVIEW_SCOPE_FIELDS = {
    "countries",
    "categories",
    "statuses",
    "required_fields",
    "source_codes",
    "result_limit",
}


def review_token_for(user, workspace_id, search):
    return signing.dumps(
        {
            "actor": str(user.pk),
            "workspace": str(workspace_id),
            "scope": search,
            "purpose": "review_only",
        },
        salt=REVIEW_SALT,
    )


def reviewed_draft_form(user, workspace_id, token):
    try:
        claim = signing.loads(token, salt=REVIEW_SALT, max_age=REVIEW_MAX_AGE_SECONDS)
    except (signing.BadSignature, TypeError, ValueError):
        raise forms.ValidationError("Suggestion expired. Request a new preview.") from None
    if (
        not isinstance(claim, dict)
        or set(claim) != {"actor", "workspace", "scope", "purpose"}
        or claim["actor"] != str(user.pk)
        or claim["workspace"] != str(workspace_id)
        or claim["purpose"] != "review_only"
        or not isinstance(claim["scope"], dict)
        or set(claim["scope"]) != REVIEW_SCOPE_FIELDS
    ):
        raise forms.ValidationError("Suggestion does not belong to this account and workspace.")
    requested = claim["scope"]
    serializer = SearchSerializer(data=requested)
    if not serializer.is_valid():
        raise forms.ValidationError("Suggestion cannot be reviewed. Open a new preview.")
    scope = serializer.validated_data
    if (
        scope != requested
        or not scope["countries"]
        or not scope["categories"]
        or any(label not in ALLOWED_CATEGORIES for label in scope["categories"])
        or scope["statuses"] != []
        or scope["source_codes"] != []
        or scope["required_fields"] != ["phone"]
        or scope["result_limit"] != 25
    ):
        raise forms.ValidationError("Suggestion scope changed. Request a new preview.")
    return DraftSearchForm(
        user=user,
        workspace_id=workspace_id,
        initial={
            "countries": scope["countries"],
            "categories": "\n".join(scope["categories"]),
            "statuses": [],
            "required_fields": ["phone"],
            "source_codes": "",
            "result_limit": scope["result_limit"],
            "draft_token": new_draft_token(user, workspace_id),
        },
    )
