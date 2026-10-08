from django.test import Client, TestCase, override_settings

from .models import Job, User


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    LOGOUT_REDIRECT_URL="http://localhost:3000/dashboard",
    CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
)
class SignOutContextTests(TestCase):
    endpoint = "/api/v1/account/sign-out-form/"

    def setUp(self):
        self.user = User.objects.create_user(username="signout-context", password="local-test-pass")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def test_context_reseeds_explicitly_and_read_does_not_log_out(self):
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)
        self.client.get("/accounts/check-session/")
        response = self.client.get(self.endpoint)
        self.assertEqual(set(response.json()), {"kind", "csrf_token"})
        self.assertEqual(response.json()["kind"], "sign-out")
        self.assertEqual(len(response.json()["csrf_token"]), 64)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(Job.objects.exists())

    def test_native_logout_requires_csrf_and_trusted_origin_then_invalidates_session(self):
        self.client.get("/accounts/check-session/")
        token = self.client.get(self.endpoint).json()["csrf_token"]
        payload = {"csrfmiddlewaretoken": token}
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertEqual(self.client.post("/accounts/logout/", {}).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/accounts/logout/", payload, HTTP_ORIGIN="https://evil.test"
            ).status_code,
            403,
        )
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(
            "/accounts/logout/", payload, HTTP_ORIGIN="http://localhost:3000"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://localhost:3000/dashboard")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)

    def test_anonymous_denial_and_write_rejection_are_private(self):
        response = Client().get(self.endpoint)
        self.assertEqual(response.status_code, 403)
        self.assertIn("no-store", response["Cache-Control"])
        self.client.get("/accounts/check-session/")
        response = self.client.post(
            self.endpoint,
            "{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 405)
        self.assertIn("no-store", response["Cache-Control"])
