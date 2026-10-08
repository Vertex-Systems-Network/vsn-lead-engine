from django.test import Client, TestCase, override_settings

from .models import Job, Membership
from .test_jobs import fixture


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
)
class NativeCancellationErrorTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.client.get("/accounts/check-session/")
        context = self.client.get(
            f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/cancel-form/"
        ).json()
        self.payload = {
            "csrfmiddlewaretoken": context["csrf_token"],
            "confirmation": context["confirmation"],
        }
        self.endpoint = f"/workspaces/{self.workspace.id}/jobs/{self.job.id}/cancel/"
        self.return_path = f"http://localhost:3000/dashboard/workspaces/{self.workspace.id}/jobs/{self.job.id}/cancel"

    def post(self, payload=None):
        return self.client.post(
            self.endpoint, payload or self.payload, HTTP_ORIGIN="http://localhost:3000"
        )

    def test_invalid_confirmation_only_returns_fixed_generic_notice(self):
        response = self.post({**self.payload, "confirmation": "forged-content"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, self.return_path + "?notice=invalid")
        self.assertIn("no-store", response["Cache-Control"])
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("draft", 0))

    def test_stale_confirmation_and_started_job_do_not_refresh_or_cancel(self):
        Job.objects.filter(pk=self.job.id).update(revision=1)
        response = self.post()
        self.assertEqual(response.url, self.return_path + "?notice=changed")
        Job.objects.filter(pk=self.job.id).update(status="running")
        self.assertEqual(self.post().status_code, 303)
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("running", 1))
        self.assertFalse(self.client.session.get("cancel_feedback"))

    def test_role_and_csrf_denial_do_not_become_recovery_redirects(self):
        self.assertEqual(
            self.post({**self.payload, "csrfmiddlewaretoken": "wrong"}).status_code, 403
        )
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertEqual(self.post().status_code, 403)
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.post().status_code, 404)
