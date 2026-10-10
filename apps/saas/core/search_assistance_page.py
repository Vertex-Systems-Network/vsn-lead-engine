"""CSRF-protected, side-effect-free search-setup suggestion preview."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .search_assistance import SearchAssistForm, search_assistance_preview
from .services import membership_for


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def search_assistance_page(request, workspace_id):
    current = membership_for(request.user, workspace_id)
    if current.role not in {"owner", "admin", "member"}:
        return HttpResponseForbidden("Workspace viewers cannot prepare new search drafts.")
    if request.method == "GET":
        if request.GET:
            return HttpResponseBadRequest("Preview does not accept query parameters.")
        return render(
            request,
            "core/search_assistance.html",
            {"workspace": current.workspace, "form": SearchAssistForm(), "preview": None},
        )
    expected = {"csrfmiddlewaretoken", "intent"}
    if set(request.POST) != expected or any(
        len(request.POST.getlist(key)) != 1 for key in expected
    ):
        return HttpResponseBadRequest("Unsupported setup preview fields.")
    form = SearchAssistForm(request.POST)
    preview, error, status = None, None, 400
    if form.is_valid():
        preview = search_assistance_preview(form.cleaned_data["intent"])
        status = 200
    else:
        error = "Enter 4–280 characters without links, phone numbers or private contact details."
    # Never echo free-form input back to the browser, even on validation errors.
    return render(
        request,
        "core/search_assistance.html",
        {
            "workspace": current.workspace,
            "form": SearchAssistForm(),
            "preview": preview,
            "error": error,
        },
        status=status,
    )
