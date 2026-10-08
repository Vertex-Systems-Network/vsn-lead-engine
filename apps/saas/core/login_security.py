from datetime import timedelta
from unicodedata import normalize

from django.conf import settings
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .account_forms import native_login, sign_in_return
from .models import LoginBucket

WINDOW = timedelta(minutes=15)
RETENTION = timedelta(days=1)
IP_LIMIT = 20
ACCOUNT_LIMIT = 10


def fingerprint(scope, value):
    return salted_hmac("saas-login:" + scope, value, algorithm="sha256").hexdigest()


@transaction.atomic
def allow_login(username, remote_addr, *, now=None):
    """Bound failed/successful attempts without disclosing account existence.

    Only the connection address is trusted; forwarded headers cannot pick a
    fresh bucket. Counts are not reset on success. PostgreSQL serializes all
    increments; SQLite remains a local smoke mode only.
    """
    now = now or timezone.now()
    LoginBucket.objects.filter(started_at__lt=now - RETENTION).delete()
    keys = [
        (fingerprint("ip", remote_addr), IP_LIMIT),
        (fingerprint("account", normalize("NFKC", username).strip().casefold()), ACCOUNT_LIMIT),
    ]
    allowed = True
    for key, limit in sorted(keys):
        LoginBucket.objects.get_or_create(fingerprint=key, defaults={"started_at": now})
        bucket = LoginBucket.objects.select_for_update().get(pk=key)
        if bucket.started_at <= now - WINDOW:
            bucket.started_at = now
            bucket.attempts = 0
        if bucket.attempts >= limit:
            allowed = False
        else:
            bucket.attempts += 1
            bucket.save(update_fields=["started_at", "attempts"])
    return allowed


class ProtectedLoginView(LoginView):
    def post(self, request, *args, **kwargs):
        if not allow_login(request.POST.get("username", ""), request.META.get("REMOTE_ADDR", "")):
            if native_login(request):
                response = HttpResponseRedirect(sign_in_return("limited"), status=303)
                response["Retry-After"] = str(int(WINDOW.total_seconds()))
                return response
            # An unbound form avoids checking credentials after the limit.
            form = self.get_form_class()(request=request)
            response = self.render_to_response(self.get_context_data(form=form, login_limited=True))
            response.status_code = 429
            response["Retry-After"] = str(int(WINDOW.total_seconds()))
            return response
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        if native_login(self.request):
            return HttpResponseRedirect(sign_in_return("invalid"), status=303)
        return super().form_invalid(form)

    def get_success_url(self):
        if native_login(self.request):
            return settings.LOGIN_REDIRECT_URL
        return super().get_success_url()
