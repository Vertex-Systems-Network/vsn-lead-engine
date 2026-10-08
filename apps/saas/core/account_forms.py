"""Explicit browser CSRF bootstrap and fixed native login return paths."""

from django.conf import settings
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .form_context import form_csrf


def native_login(request):
    return bool(settings.WEB_DASHBOARD_URL) and request.POST.getlist("native_login") == ["1"]


def sign_in_return(notice=None):
    url = settings.WEB_DASHBOARD_URL.removesuffix("/dashboard") + "/account/sign-in"
    return url + (f"?notice={notice}" if notice in {"invalid", "limited"} else "")


@never_cache
@require_GET
@ensure_csrf_cookie
def start_sign_in(request):
    get_token(request)
    return HttpResponseRedirect(
        sign_in_return() if settings.WEB_DASHBOARD_URL else settings.LOGIN_URL, status=303
    )


@never_cache
@require_GET
def sign_in_form(request):
    from rest_framework.exceptions import PermissionDenied

    try:
        token = form_csrf(request)
    except PermissionDenied:
        return HttpResponseForbidden("Start sign-in to prepare this browser.")
    return JsonResponse({"kind": "sign-in", "csrf_token": token})
