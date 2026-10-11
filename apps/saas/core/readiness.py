"""Default-disabled database reachability probe for private staging ingress only.

This is deliberately not a migration, worker, source, email or launch check.
A reverse proxy must deny public access before this opt-in route is enabled.
"""

from django.conf import settings
from django.db import connections
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def internal_readiness(request):
    if not settings.SAAS_INTERNAL_READINESS_ENABLED:
        raise Http404("Unavailable.")
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            ready = cursor.fetchone() == (1,)
    except Exception:
        # Never reflect connection strings, SQL or provider errors to clients.
        ready = False
    return JsonResponse(
        {"status": "ready" if ready else "unavailable"},
        status=200 if ready else 503,
    )
