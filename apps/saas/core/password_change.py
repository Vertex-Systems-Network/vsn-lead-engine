"""Authenticated self-service password change with conservative browser caching."""

from django.contrib.auth import views as auth_views
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache


@method_decorator(never_cache, name="dispatch")
class PrivatePasswordChangeView(auth_views.PasswordChangeView):
    """Require the current password; Django rotates the active session hash."""

    template_name = "registration/password_change_form.html"


@method_decorator(never_cache, name="dispatch")
class PrivatePasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    """Django's authenticated completion page; no private browser caching."""

    template_name = "registration/password_change_done.html"
