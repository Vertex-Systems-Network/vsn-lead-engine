"""Authenticated self-service password change with conservative browser caching."""

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from .login_security import WINDOW, allow_login


@method_decorator(never_cache, name="dispatch")
class PrivatePasswordChangeView(auth_views.PasswordChangeView):
    """Require the current password; Django rotates the active session hash."""

    template_name = "registration/password_change_form.html"

    def post(self, request, *args, **kwargs):
        # LoginRequiredMixin in PasswordChangeView.dispatch authenticates first.
        # Rate limit before hashing/validating submitted passwords; never store
        # plaintext credentials or a raw account/IP identifier in the bucket.
        key = f"password-change:{request.user.pk}"
        if not allow_login(key, request.META.get("REMOTE_ADDR", "")):
            form = self.get_form_class()(user=request.user)
            response = self.render_to_response(self.get_context_data(form=form, limited=True))
            response.status_code = 429
            response["Retry-After"] = str(int(WINDOW.total_seconds()))
            return response
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "dashboard_url": settings.WEB_DASHBOARD_URL or "/",
        }


@method_decorator(never_cache, name="dispatch")
class PrivatePasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    """Django's authenticated completion page; no private browser caching."""

    template_name = "registration/password_change_done.html"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "dashboard_url": settings.WEB_DASHBOARD_URL or "/",
        }
