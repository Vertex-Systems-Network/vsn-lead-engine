import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from django.core import mail
from django.test import TestCase, override_settings

from .login_security import ACCOUNT_LIMIT, IP_LIMIT, allow_login, fingerprint
from .models import LoginBucket, User

PASSWORD = "original-passphrase-5521"
NEW = "replacement-passphrase-8812"


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-owner", email="owner@reset.example", password=PASSWORD
        )

    def request_reset(self, email="owner@reset.example"):
        return self.client.post("/accounts/password-reset/", {"email": email})

    def test_reset_link_sets_a_new_password_once(self):
        self.assertContains(self.client.get("/accounts/login/"), "Forgot your password?")
        response = self.request_reset("OWNER@reset.example")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://[^/\s]+(/accounts/reset/\S+/)", mail.outbox[0].body).group(1)
        form_page = self.client.get(link, follow=True)
        self.assertContains(form_page, "Choose a new password")
        set_url = form_page.redirect_chain[-1][0]
        done = self.client.post(set_url, {"new_password1": NEW, "new_password2": NEW})
        self.assertRedirects(done, "/accounts/reset/done/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertContains(self.client.get(link, follow=True), "Link expired")

    def test_unknown_address_gets_the_same_response_and_no_email(self):
        response = self.request_reset("nobody@reset.example")
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(mail.outbox, [])

    def test_requests_are_rate_limited_across_case_variants(self):
        for index in range(ACCOUNT_LIMIT):
            response = self.request_reset(
                "OWNER@RESET.EXAMPLE" if index % 2 else "owner@reset.example"
            )
            self.assertEqual(response.status_code, 302)
        response = self.request_reset("Owner@Reset.Example")
        self.assertContains(response, "Too many requests", status_code=429)
        self.assertEqual(response["Retry-After"], "900")
        self.assertEqual(len(mail.outbox), ACCOUNT_LIMIT)
        self.assertEqual(LoginBucket.objects.count(), 2)
        self.assertFalse(LoginBucket.objects.filter(pk=fingerprint("ip", "127.0.0.1")).exists())
        self.assertFalse(
            LoginBucket.objects.filter(
                pk=fingerprint("account", "reset:owner@reset.example")
            ).exists()
        )

    def test_reset_ip_limit_does_not_block_login_or_signup(self):
        for index in range(IP_LIMIT):
            response = self.client.post(
                "/accounts/password-reset/",
                {"email": f"unknown-{index}@synthetic.invalid"},
                HTTP_X_FORWARDED_FOR=f"198.51.100.{index}",
            )
            self.assertEqual(response.status_code, 302)
        denied = self.client.post(
            "/accounts/password-reset/",
            {"email": "never-seen@synthetic.invalid"},
            HTTP_X_FORWARDED_FOR="203.0.113.9",
        )
        self.assertContains(denied, "Too many requests", status_code=429)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            self.client.post(
                "/accounts/login/",
                {"username": self.user.username, "password": PASSWORD},
            ).status_code,
            302,
        )
        self.client.logout()
        with override_settings(SAAS_SIGNUP_ENABLED=True, SAAS_STARTER_ENTITLEMENT={}):
            signup = self.client.post(
                "/accounts/sign-up/",
                {
                    "username": "new-after-reset",
                    "email": "new-after-reset@synthetic.invalid",
                    "password1": "extra-long-unique-signup-passphrase-9431",
                    "password2": "extra-long-unique-signup-passphrase-9431",
                    "workspace_name": "Recovery-safe test",
                },
            )
        self.assertEqual(signup.status_code, 303)
        self.assertTrue(User.objects.filter(username="new-after-reset").exists())

    def test_exhausted_login_budget_does_not_block_recovery(self):
        for index in range(IP_LIMIT):
            self.assertTrue(allow_login(f"no-such-user-{index}", "127.0.0.1"))
        response = self.request_reset()
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(LoginBucket.objects.count(), IP_LIMIT + 3)

    def test_unsupported_rate_limit_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            allow_login(self.user.email, "127.0.0.1", bucket_scope="unscoped")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
class UndeliverablePasswordResetTests(TestCase):
    """No SMTP: reset secrets must not go into process output."""

    def test_reset_remains_generic_and_never_prints_a_bearer_link(self):
        User.objects.create_user(
            username="no-smtp-user",
            email="no-smtp@synthetic.invalid",
            password="synthetic-local-passphrase",
        )
        output = StringIO()
        with redirect_stdout(output):
            known = self.client.post(
                "/accounts/password-reset/", {"email": "no-smtp@synthetic.invalid"}
            )
            unknown = self.client.post(
                "/accounts/password-reset/", {"email": "unknown@synthetic.invalid"}
            )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.url, unknown.url)
        self.assertEqual(known.url, "/accounts/password-reset/sent/")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(mail.outbox, [])

    def test_non_debug_settings_select_discard_backend_without_smtp(self):
        env = {
            **os.environ,
            "SAAS_DEBUG": "0",
            "SAAS_SECRET_KEY": "synthetic-test-setting-not-a-production-secret",
            "SAAS_EMAIL_HOST": "",
        }
        result = subprocess.run(
            [sys.executable, "-c", "from lead_saas import settings; print(settings.EMAIL_BACKEND)"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        self.assertEqual(result.stdout.strip(), "django.core.mail.backends.dummy.EmailBackend")
        self.assertEqual(result.stderr, "")
