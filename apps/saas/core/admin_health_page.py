"""Read-only owner/admin operational health page with no provider secrets."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .admin_health import operational_health


@never_cache
@login_required
@require_GET
def admin_operational_health_page(request, workspace_id):
    # No query filters; every aggregate uses the authoritative URL tenant scope.
    if request.GET:
        return HttpResponseBadRequest("Operations snapshot accepts no query parameters.")
    report = operational_health(request.user, workspace_id)
    return render(
        request,
        "core/admin_operational_health.html",
        {"workspace": request.user.membership_set.get(workspace_id=workspace_id).workspace, "report": report},
    )
