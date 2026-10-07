from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from lead_saas.web_origin import dashboard_return

from .models import LoginBucket, User


class WebOriginTests(SimpleTestCase):
    def test_fixed_origin_and_development_loopback_only(self):
        self.assertIsNone(dashboard_return("", debug=False))
        self.assertEqual(
            dashboard_return("https://web.example.test/", debug=False),
            "https://web.example.test/dashboard",
        )
        for origin in ["http://localhost:3000", "http://127.0.0.1:3000", "http://[::1]:3000"]:
            self.assertTrue(dashboard_return(origin, debug=True).endswith("/dashboard"))
            with self.assertRaises(ImproperlyConfigured):
                dashboard_return(origin, debug=False)

    def test_credentials_paths_queries_controls_and_remote_http_fail_closed(self):
        for origin in [
            "http://web.example.test",
            "https://*.example.test",
            "//web.example.test",
            "https://user:secret@web.example.test",
            "https://@web.example.test",
            "https://web.example.test/path",
            "https://web.example.test?q=1",
            "https://web.example.test/#next",
            "https://web.example.test:99999",
            "https://web.example.test:0",
            "https://web.example.test?",
            "https://web.example.test#",
            "https://web.example.test\\path",
            "https://web.example.test\x7f",
            "https://web.example.test\n",
            "https://[broken",
            None,
            "https://" + "a" * 2050,
        ]:
            with self.subTest(origin=origin), self.assertRaises(ImproperlyConfigured):
                dashboard_return(origin, debug=True)


@override_settings(
    LOGIN_REDIRECT_URL="http://localhost:3000/dashboard",
    LOGOUT_REDIRECT_URL="http://localhost:3000/dashboard",
)
class SessionNavigationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="session-nav", password="disposable-test-password"
        )
        self.client = Client(enforce_csrf_checks=True)

    def login(self, next=""):
        self.client.get("/accounts/login/")
        return self.client.post(
            "/accounts/login/",
            {
                "username": self.user.username,
                "password": "disposable-test-password",
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                "next": next,
            },
        )

    def test_login_defaults_to_fixed_dashboard_and_external_next_cannot_choose_host(self):
        for target in [
            "",
            "https://evil.example.test/",
            "//evil.example.test/",
            "http://localhost:3999/dashboard",
        ]:
            self.client.logout()
            response = self.login(target)
            self.assertRedirects(
                response, "http://localhost:3000/dashboard", fetch_redirect_response=False
            )
        self.assertEqual(LoginBucket.objects.filter(attempts=4).count(), 2)

    def test_backend_local_next_still_works_and_login_csrf_is_required(self):
        response = self.client.post(
            "/accounts/login/",
            {"username": self.user.username, "password": "disposable-test-password"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LoginBucket.objects.exists())
        self.assertRedirects(
            self.login("/accounts/sign-out/"), "/accounts/sign-out/", fetch_redirect_response=False
        )

    def test_confirmation_is_non_mutating_and_logout_requires_csrf_post(self):
        self.login()
        response = self.client.get("/accounts/sign-out/")
        self.assertContains(response, "End your session")
        self.assertContains(response, 'action="/accounts/logout/"')
        self.assertContains(response, "http://localhost:3000/dashboard")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 403)
        self.assertIn("_auth_user_id", self.client.session)
        forged = self.client.post(
            "/accounts/logout/",
            {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value},
            HTTP_ORIGIN="https://evil.example.test",
        )
        self.assertEqual(forged.status_code, 403)
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(
            "/accounts/logout/",
            {
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                "next": "https://evil.example.test/",
            },
        )
        self.assertRedirects(
            response, "http://localhost:3000/dashboard", fetch_redirect_response=False
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_anonymous_confirmation_redirects_to_login_and_post_cannot_skip_confirmation(self):
        self.assertRedirects(
            self.client.get("/accounts/sign-out/"),
            "/accounts/login/?next=/accounts/sign-out/",
            fetch_redirect_response=False,
        )
        self.login()
        response = self.client.post(
            "/accounts/sign-out/", {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value}
        )
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
