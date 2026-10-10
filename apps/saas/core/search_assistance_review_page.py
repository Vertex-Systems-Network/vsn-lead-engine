"""Explicit CSRF-only preview-to-editable-draft handoff with zero writes."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .search_assistance_review import reviewed_draft_form
from .services import membership_for


@never_cache
@login_required
@require_POST
def search_assistance_review_page(request, workspace_id):
    current = membership_for(request.user, workspace_id)
    if current.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("Viewers cannot prepare draft searches.")
    if request.GET:
        return HttpResponseBadRequest("Review does not accept query parameters.")
    expected = {"csrfmiddlewaretoken", "review_token"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported review fields.")
    token = request.POST["review_token"]
    if not token or len(token) > 2048:
        return HttpResponseBadRequest("Invalid review token.")
    try:
        form = reviewed_draft_form(request.user, workspace_id, token)
    except forms.ValidationError:
        return HttpResponseBadRequest("Review unavailable. Open a fresh local preview.")
    return render(
        request,
        "core/search_assistance_review.html",
        {"workspace": current.workspace, "form": form},
    )
