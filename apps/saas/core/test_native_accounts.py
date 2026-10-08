from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings

from .login_security import ACCOUNT_LIMIT, allow_login
from .models import Job, LoginBucket, User


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    LOGIN_REDIRECT_URL="http://localhost:3000/dashboard",
    CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
)
class NativeAccountTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(username="native-account", password="local-pass-only")

    def prepare(self):
        self.client.get("/accounts/start-sign-in/")
        return self.client.get("/api/v1/account/sign-in-form/").json()["csrf_token"]

    def payload(self):
        return {
            "csrfmiddlewaretoken": self.prepare(),
            "username": self.user.username,
            "password": "local-pass-only",
            "native_login": "1",
        }

    def test_explicit_bootstrap_fixed_return_and_stateless_private_context(self):
        missing = self.client.get("/api/v1/account/sign-in-form/")
        self.assertEqual(missing.status_code, 403)
        self.assertNotIn("csrftoken", missing.cookies)
        response = self.client.get("/accounts/start-sign-in/?next=https://evil.test/")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, "http://localhost:3000/account/sign-in")
        self.assertIn("csrftoken", response.cookies)
        response = self.client.get("/api/v1/account/sign-in-form/")
        self.assertEqual(set(response.json()), {"kind", "csrf_token"})
        self.assertEqual(response.json()["kind"], "sign-in")
        self.assertEqual(len(response.json()["csrf_token"]), 64)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(LoginBucket.objects.exists())
        self.assertFalse(Job.objects.exists())
        self.assertEqual(self.client.post("/api/v1/account/sign-in-form/").status_code, 403)
        self.assertEqual(self.client.post("/accounts/start-sign-in/").status_code, 403)
        cookie = self.client.cookies["csrftoken"].value
        for path in ["/api/v1/account/sign-in-form/", "/accounts/start-sign-in/"]:
            self.assertEqual(self.client.post(path, {}, HTTP_X_CSRFTOKEN=cookie).status_code, 405)
        with override_settings(WEB_DASHBOARD_URL=""):
            self.assertEqual(self.client.get("/accounts/start-sign-in/").url, "/accounts/login/")

    def test_login_requires_csrf_and_trusted_origin_before_budget_or_auth(self):
        data = self.payload()
        self.assertEqual(
            self.client.post(
                "/accounts/login/", {**data, "csrfmiddlewaretoken": "wrong"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/accounts/login/", data, HTTP_ORIGIN="https://evil.test").status_code,
            403,
        )
        self.assertFalse(LoginBucket.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_invalid_credentials_only_return_generic_notice_without_preserving_credentials(self):
        data = self.payload()
        for username in [self.user.username, "unknown-user"]:
            response = self.client.post(
                "/accounts/login/",
                {**data, "username": username, "password": "secret-never-store"},
                HTTP_ORIGIN="http://localhost:3000",
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.url, "http://localhost:3000/account/sign-in?notice=invalid")
            self.assertNotIn("secret-never-store", repr(dict(self.client.session)))
            self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(
            "/accounts/login/", {**data, "native_login": "0", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)

    def test_native_success_ignores_next_rotates_session_and_csrf(self):
        data = self.payload()
        session = self.client.session
        session["probe"] = "anonymous"
        session.save()
        old = session.session_key
        csrf_cookie = self.client.cookies["csrftoken"].value
        response = self.client.post(
            "/accounts/login/?next=/health/",
            {**data, "next": "/health/"},
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://localhost:3000/dashboard")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertFalse(Session.objects.filter(pk=old).exists())
        self.assertNotEqual(self.client.cookies["csrftoken"].value, csrf_cookie)
        self.assertEqual(self.client.post("/accounts/login/", data).status_code, 403)

    def test_native_rate_limit_keeps_existing_cap_without_checking_credentials(self):
        data = self.payload()
        for _ in range(ACCOUNT_LIMIT):
            self.assertTrue(allow_login(self.user.username, "127.0.0.1"))
        with patch(
            "django.contrib.auth.forms.AuthenticationForm.is_valid",
            side_effect=AssertionError("credentials must not be checked"),
        ):
            response = self.client.post(
                "/accounts/login/", data, HTTP_ORIGIN="http://localhost:3000"
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, "http://localhost:3000/account/sign-in?notice=limited")
        self.assertEqual(response["Retry-After"], "900")
        self.assertNotIn("_auth_user_id", self.client.session)
