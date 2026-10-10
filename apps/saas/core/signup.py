"""Self-service sign-up: account, owned workspace and optional starter allowance."""

from django import forms
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .login_security import WINDOW, allow_login
from .models import Entitlement, User
from .services import create_workspace

NOTICES = {"invalid", "taken", "limited"}


class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, help_text="Used for password reset.")
    workspace_name = forms.CharField(max_length=120, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email


def native_signup(request):
    return bool(settings.WEB_DASHBOARD_URL) and request.POST.getlist("native_signup") == ["1"]


def sign_up_return(notice):
    url = settings.WEB_DASHBOARD_URL.removesuffix("/dashboard") + "/account/sign-up"
    return url + (f"?notice={notice}" if notice in NOTICES else "")


@transaction.atomic
def register(form):
    user = form.save()
    name = form.cleaned_data["workspace_name"].strip() or f"{user.username}'s workspace"
    workspace = create_workspace(user, {"name": name[:120], "timezone": "UTC"})
    if settings.SAAS_STARTER_ENTITLEMENT:
        Entitlement.objects.create(
            workspace=workspace, active=True, **settings.SAAS_STARTER_ENTITLEMENT
        )
    return user


@never_cache
@require_http_methods(["GET", "POST"])
def sign_up_page(request):
    if not settings.SAAS_SIGNUP_ENABLED:
        raise Http404("Sign-up is not available.")
    native = request.method == "POST" and native_signup(request)
    if request.method == "GET":
        return render(request, "registration/sign_up.html", {"form": SignUpForm()})
    if not allow_login(request.POST.get("username", ""), request.META.get("REMOTE_ADDR", "")):
        if native:
            response = HttpResponseRedirect(sign_up_return("limited"), status=303)
        else:
            response = render(
                request,
                "registration/sign_up.html",
                {"form": SignUpForm(), "limited": True},
                status=429,
            )
        response["Retry-After"] = str(int(WINDOW.total_seconds()))
        return response
    form = SignUpForm(request.POST)
    if not form.is_valid():
        if native:
            username = request.POST.get("username", "")
            email = request.POST.get("email", "").strip()
            taken = (
                "username" in form.errors
                and User.objects.filter(username__iexact=username).exists()
            ) or ("email" in form.errors and User.objects.filter(email__iexact=email).exists())
            return HttpResponseRedirect(sign_up_return("taken" if taken else "invalid"), status=303)
        return render(request, "registration/sign_up.html", {"form": form}, status=400)
    user = register(form)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return HttpResponseRedirect(settings.WEB_DASHBOARD_URL or "/", status=303)
