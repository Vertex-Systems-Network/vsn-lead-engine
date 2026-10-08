"""Bounded session-only validation handoff; never grants draft authority."""

import uuid
from time import time

from django.core.exceptions import ValidationError
from django.http import Http404

KEY = "draft_feedback_v1"
TTL = 300
MAX_ENTRIES = 3
SCALARS = {"categories": 1600, "source_codes": 900, "result_limit": 40}
LISTS = ("countries", "statuses", "required_fields")
ERROR_FIELDS = {*SCALARS, *LISTS, "__all__"}


def save_feedback(request, workspace_id, form, status):
    # Invalid/expired authority and oversized submissions retain the Django fallback.
    token = form.cleaned_data.get("draft_token")
    if not token or not form.key:
        return None
    values = {}
    for field, limit in SCALARS.items():
        entries = request.POST.getlist(field)
        if len(entries) > 1 or any(len(value) > limit for value in entries):
            return None
        values[field] = entries[0] if entries else ""
    for field in LISTS:
        entries = request.POST.getlist(field)
        if len(entries) > 12 or any(len(value) > 64 for value in entries):
            return None
        values[field] = entries
    errors = {field: [str(e) for e in messages] for field, messages in form.errors.items()}
    if set(errors) - ERROR_FIELDS or any(
        len(messages) > 5 or any(len(message) > 240 for message in messages)
        for messages in errors.values()
    ):
        return None
    now = time()
    entries = request.session.get(KEY, {})
    entries = {key: value for key, value in entries.items() if value["expires"] > now}
    entries = dict(list(entries.items())[-(MAX_ENTRIES - 1) :])
    handle = str(uuid.uuid4())
    entries[handle] = {
        "actor": str(request.user.pk),
        "workspace": str(workspace_id),
        "expires": now + TTL,
        "values": values,
        "errors": errors,
        "draft_token": token,
        "status": status,
    }
    request.session[KEY] = entries
    return handle


def feedback_for(request, workspace_id, handle):
    from .forms import DraftSearchForm

    entry = request.session.get(KEY, {}).get(str(handle))
    if (
        not entry
        or entry["actor"] != str(request.user.pk)
        or entry["workspace"] != str(workspace_id)
        or entry["expires"] <= time()
    ):
        raise Http404
    # Verify original nonce again; feedback cannot refresh an expired draft identity.
    form = DraftSearchForm(user=request.user, workspace_id=workspace_id)
    form.cleaned_data = {"draft_token": entry["draft_token"]}
    try:
        form.clean_draft_token()
    except ValidationError:
        raise Http404 from None
    return {key: entry[key] for key in ("values", "errors", "draft_token", "status")}
