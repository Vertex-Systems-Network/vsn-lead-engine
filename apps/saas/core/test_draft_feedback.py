from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core import signing
from django.test import Client, TestCase, override_settings

from .draft_feedback import KEY
from .forms import TOKEN_SALT
from .models import Job, JobOutbox, Membership, UsageReservation, User
from .services import create_workspace
from .test_jobs import fixture


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
)
class DraftFeedbackTests(TestCase):
    def setUp(self):
        self.user, self.workspace, _ = fixture()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.client.get("/accounts/check-session/")
        context = self.client.get(f"/api/v1/workspaces/{self.workspace.id}/draft-form/").json()
        self.payload = {
            "countries": ["US", "CA"],
            "categories": "<script>bakery</script>",
            "result_limit": "0",
            "draft_token": context["draft_token"],
            "csrfmiddlewaretoken": context["csrf_token"],
        }
        self.submit = f"/workspaces/{self.workspace.id}/search/new/"

    def post(self, data=None):
        return self.client.post(
            self.submit, data or self.payload, HTTP_ORIGIN="http://localhost:3000"
        )

    def endpoint(self, response, workspace=None):
        self.assertEqual(response.status_code, 303)
        handle = parse_qs(urlparse(response.url).query)["feedback"][0]
        return f"/api/v1/workspaces/{workspace or self.workspace.id}/draft-feedback/{handle}/"

    def test_preservation_correction_and_replay_keep_original_identity(self):
        response = self.post()
        self.assertNotIn("script", response.url)
        self.assertIn(f"/workspaces/{self.workspace.id}/search/new?feedback=", response.url)
        endpoint = self.endpoint(response)
        before = dict(self.client.session[KEY])
        for _ in range(2):
            read = self.client.get(endpoint)
            data = read.json()
            self.assertEqual(data["kind"], "draft-feedback")
            self.assertEqual(data["values"]["categories"], self.payload["categories"])
            self.assertEqual(data["values"]["countries"], ["US", "CA"])
            self.assertEqual(data["draft_token"], self.payload["draft_token"])
            self.assertEqual(data["status"], 400)
            self.assertIn("result_limit", data["errors"])
            self.assertIn("private", read["Cache-Control"])
            self.assertIn("no-store", read["Cache-Control"])
        self.assertEqual(self.client.session[KEY], before)
        self.assertEqual(Job.objects.count(), 1)
        corrected = {**self.payload, "result_limit": "5", "csrfmiddlewaretoken": data["csrf_token"]}
        first = self.post(corrected)
        self.assertEqual(self.post(corrected).url, first.url)
        self.assertEqual(Job.objects.count(), 2)
        conflict = self.client.get(
            self.endpoint(self.post({**corrected, "result_limit": "6"}))
        ).json()
        self.assertEqual(conflict["status"], 409)
        self.assertIn("__all__", conflict["errors"])
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())

    def test_expiry_revocation_other_session_and_workspace_fail_closed(self):
        response = self.post()
        endpoint = self.endpoint(response)
        another = Client()
        another.force_login(self.user)
        another.get("/accounts/check-session/")
        self.assertEqual(another.get(endpoint).status_code, 404)
        foreign = create_workspace(
            User.objects.create_user(username="foreign-feedback"),
            {"name": "Foreign", "timezone": "UTC"},
        )
        self.assertEqual(self.client.get(self.endpoint(response, foreign.id)).status_code, 404)
        with patch("core.draft_feedback.time", return_value=10**12):
            self.assertEqual(self.client.get(endpoint).status_code, 404)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(Job.objects.count(), 1)

    def test_entry_cap_and_no_unknown_fields_or_raw_csrf_in_storage(self):
        endpoints = []
        for _ in range(4):
            endpoints.append(
                self.endpoint(self.post({**self.payload, "password": "never-store-me"}))
            )
        self.assertEqual(len(self.client.session[KEY]), 3)
        self.assertEqual(self.client.get(endpoints[0]).status_code, 404)
        stored = repr(self.client.session[KEY])
        self.assertNotIn("never-store-me", stored)
        self.assertNotIn(self.client.cookies["csrftoken"].value, stored)

    def test_invalid_authority_oversized_or_repeated_scalar_uses_backend_fallback(self):
        for changes in [
            {"draft_token": "forged"},
            {"categories": "x" * 1601},
            {"categories": ["one", "two"]},
            {"countries": ["US"] * 13},
        ]:
            self.assertEqual(self.post({**self.payload, **changes}).status_code, 400)
        self.assertNotIn(KEY, self.client.session)
        self.assertEqual(Job.objects.count(), 1)

    def test_csrf_denial_no_feedback_and_logout_loses_handoff(self):
        self.assertEqual(
            self.post({**self.payload, "csrfmiddlewaretoken": "wrong"}).status_code, 403
        )
        self.assertNotIn(KEY, self.client.session)
        endpoint = self.endpoint(self.post())
        self.client.post(
            "/accounts/logout/", {"csrfmiddlewaretoken": self.payload["csrfmiddlewaretoken"]}
        )
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.assertNotIn(KEY, self.client.session)

    def test_cookie_rotation_and_original_token_expiry_are_rechecked(self):
        endpoint = self.endpoint(self.post())
        self.client.cookies.pop("csrftoken")
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.client.get("/accounts/check-session/")
        data = self.client.get(endpoint).json()
        self.assertNotEqual(data["csrf_token"], self.payload["csrfmiddlewaretoken"])
        session = self.client.session
        entry = next(iter(session[KEY].values()))
        original = signing.loads(entry["draft_token"], salt=TOKEN_SALT)
        with patch("django.core.signing.time.time", return_value=0):
            entry["draft_token"] = signing.dumps(original, salt=TOKEN_SALT)
        session.save()
        self.assertEqual(self.client.get(endpoint).status_code, 404)
