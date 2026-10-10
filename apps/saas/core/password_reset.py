"""Email password reset on Django's built-in token views, with request rate limits."""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .login_security import WINDOW, allow_login


class LimitedPasswordResetView(auth_views.PasswordResetView):
    """Same response whether or not the address exists; bounded per address and IP."""

    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "")
        if not allow_login("reset:" + email, request.META.get("REMOTE_ADDR", "")):
            response = self.render_to_response(
                self.get_context_data(form=self.get_form_class()(), limited=True)
            )
            response.status_code = 429
            response["Retry-After"] = str(int(WINDOW.total_seconds()))
            return response
        return super().post(request, *args, **kwargs)


urlpatterns = [
    path(
        "accounts/password-reset/",
        LimitedPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
