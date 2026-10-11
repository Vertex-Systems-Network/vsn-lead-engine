"""Synthetic account-security regressions using real sessions and Django forms."""

import re
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .login_security import ACCOUNT_LIMIT, WINDOW
from .models import LoginBucket, User

OLD = "original-account-passphrase-5521"
NEW = "changed-account-passphrase-8812"


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    LOGIN_REDIRECT_URL="http://localhost:3000/dashboard",
)
class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="change-owner", email="change@synthetic.invalid", password=OLD
        )
        self.browser = Client(enforce_csrf_checks=True)
        self.browser.force_login(self.user)
        self.other_browser = Client()
        self.other_browser.force_login(self.user)

    def valid(self, **changes):
        return {
            "old_password": OLD,
            "new_password1": NEW,
            "new_password2": NEW,
            **changes,
        }

    def post(self, **changes):
        return self.browser.post(
            "/accounts/password-change/",
            self.valid(**changes),
            HTTP_X_CSRFTOKEN=self.browser.cookies["csrftoken"].value,
        )

    def test_requires_authenticated_account_and_csrf(self):
        anon = Client()
        response = anon.get("/accounts/password-change/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/accounts/login/?next="))
        self.assertEqual(anon.post("/accounts/password-change/", self.valid()).status_code, 302)
        self.assertEqual(anon.get("/accounts/password-change/done/").status_code, 302)
        self.assertEqual(
            self.browser.post("/accounts/password-change/", self.valid()).status_code, 403
        )

        page = self.browser.get("/accounts/password-change/")
        self.assertContains(page, "Change your password")
        self.assertContains(page, 'autocomplete="current-password"')
        self.assertContains(page, 'autocomplete="new-password"')
        self.assertIn("no-store", page["Cache-Control"])
        self.assertIn("private", page["Cache-Control"])
        self.assertIn("csrftoken", self.browser.cookies)
        self.assertEqual(
            self.browser.post(
                "/accounts/password-change/",
                self.valid(),
                HTTP_X_CSRFTOKEN=self.browser.cookies["csrftoken"].value,
                HTTP_ORIGIN="https://malicious.invalid",
            ).status_code,
            403,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))
        self.assertEqual(LoginBucket.objects.count(), 2)

    def test_wrong_or_weak_password_does_not_mutate_or_end_session(self):
        self.browser.get("/accounts/password-change/")
        wrong = self.post(old_password="incorrect-passphrase")
        self.assertContains(wrong, "Your old password was entered incorrectly", status_code=200)
        weak = self.post(new_password1="123", new_password2="123")
        self.assertContains(weak, "too short", status_code=200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))
        self.assertIn("_auth_user_id", self.browser.session)
        self.assertIn("_auth_user_id", self.other_browser.session)

    def test_real_change_rotates_active_session_and_revokes_other_sessions(self):
        self.browser.get("/accounts/password-change/")
        previous_session = self.browser.session.session_key
        changed = self.post()
        self.assertRedirects(
            changed,
            "/accounts/password-change/done/",
            fetch_redirect_response=False,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertIsNone(authenticate(username=self.user.username, password=OLD))
        self.assertIsNotNone(authenticate(username=self.user.username, password=NEW))
        self.assertNotEqual(self.browser.session.session_key, previous_session)
        self.assertEqual(self.browser.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(self.browser.get("/api/v1/workspaces/").status_code, 200)
        done = self.browser.get("/accounts/password-change/done/")
        self.assertContains(done, "Password updated")
        self.assertIn("no-store", done["Cache-Control"])
        self.assertIn("private", done["Cache-Control"])
        self.assertEqual(self.other_browser.get("/api/v1/workspaces/").status_code, 403)
        self.assertEqual(self.other_browser.get("/accounts/password-change/done/").status_code, 302)
        self.assertEqual(LoginBucket.objects.count(), 2)

    def test_authenticated_change_attempts_are_bounded_before_password_validation(self):
        self.browser.get("/accounts/password-change/")
        old = self.browser.session.session_key
        for index in range(ACCOUNT_LIMIT):
            response = self.post(old_password=f"incorrect-pass-{index}")
            self.assertEqual(response.status_code, 200)
        with patch(
            "django.contrib.auth.forms.PasswordChangeForm.is_valid",
            side_effect=AssertionError("No password validation after rate limit"),
        ):
            response = self.post(old_password="secret-must-not-be-reflected")
        self.assertContains(response, "Too many password change attempts", status_code=429)
        self.assertEqual(response["Retry-After"], str(int(WINDOW.total_seconds())))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertNotContains(response, "secret-must-not-be-reflected", status_code=429)
        self.assertEqual(self.browser.session.session_key, old)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))
        self.assertIn("_auth_user_id", self.other_browser.session)
        self.assertEqual(LoginBucket.objects.count(), 2)

    def test_rate_limit_cannot_be_bypassed_with_forwarded_ip_or_guest_request(self):
        self.browser.get("/accounts/password-change/")
        for index in range(ACCOUNT_LIMIT):
            self.assertEqual(
                self.browser.post(
                    "/accounts/password-change/",
                    self.valid(old_password="wrong"),
                    HTTP_X_CSRFTOKEN=self.browser.cookies["csrftoken"].value,
                    HTTP_X_FORWARDED_FOR=f"198.51.100.{index}",
                ).status_code,
                200,
            )
        denial = self.browser.post(
            "/accounts/password-change/",
            self.valid(old_password=OLD),
            HTTP_X_CSRFTOKEN=self.browser.cookies["csrftoken"].value,
            HTTP_X_FORWARDED_FOR="203.0.113.5",
        )
        self.assertEqual(denial.status_code, 429)
        self.assertEqual(Client().post("/accounts/password-change/", self.valid()).status_code, 302)
        self.assertEqual(LoginBucket.objects.count(), 2)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_attempt_budget_expires_after_fixed_window(self):
        self.browser.get("/accounts/password-change/")
        now = timezone.now()
        with patch("core.login_security.timezone.now", return_value=now):
            for _ in range(ACCOUNT_LIMIT):
                self.assertEqual(self.post(old_password="wrong").status_code, 200)
            self.assertEqual(self.post().status_code, 429)
        with patch("core.login_security.timezone.now", return_value=now + WINDOW):
            recovered = self.post()
        self.assertEqual(recovered.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertIn("_auth_user_id", self.browser.session)

    def test_change_invalidates_existing_email_reset_token(self):
        self.browser.get("/accounts/password-reset/")
        response = self.browser.post(
            "/accounts/password-reset/",
            {"email": self.user.email},
            HTTP_X_CSRFTOKEN=self.browser.cookies["csrftoken"].value,
        )
        self.assertRedirects(response, "/accounts/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://[^/\s]+(/accounts/reset/\S+/)", mail.outbox[0].body).group(1)
        self.browser.get("/accounts/password-change/")
        self.assertEqual(self.post().status_code, 302)
        expired = self.browser.get(link, follow=True)
        self.assertContains(expired, "Link expired")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
