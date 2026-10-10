from django.test import TestCase, override_settings

from .cancellation_forms import cancellation_token, submission_token
from .models import Entitlement, Job, JobOutbox, Membership, User
from .services import create_draft, create_workspace
from .test_jobs import fixture


class SubmitWebTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        self.client.force_login(self.user)
        self.detail = f"/workspaces/{self.workspace.id}/jobs/{self.job.id}/"
        self.page = f"{self.detail}submit/"

    def token(self):
        self.job.refresh_from_db()
        return submission_token(self.user, self.workspace.id, self.job)

    def test_draft_submit_reserves_and_queues_once(self):
        self.assertContains(self.client.get(self.detail), "Submit job")
        response = self.client.get(self.page)
        self.assertContains(response, "Confirm and submit")
        self.assertContains(response, "at most 25 new leads")
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("draft", 0))
        data = {"confirmation": response.context["form"].initial["confirmation"]}
        first = self.client.post(self.page, data)
        self.assertEqual((first.status_code, first.url), (303, self.detail))
        self.assertEqual(self.client.post(self.page, data).status_code, 303)
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("queued", 1))
        outbox = JobOutbox.objects.get(job=self.job)
        self.assertEqual((outbox.status, outbox.reservation.status), ("pending", "reserved"))
        self.assertNotContains(self.client.get(self.detail), "Submit job")
        self.assertEqual(self.client.get(self.page).status_code, 409)

    def test_cancellation_token_cannot_submit(self):
        data = {"confirmation": cancellation_token(self.user, self.workspace.id, self.job)}
        self.assertEqual(self.client.post(self.page, data).status_code, 400)
        self.assertFalse(JobOutbox.objects.exists())

    def test_inactive_entitlement_is_explained_without_queueing(self):
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        response = self.client.post(self.page, {"confirmation": self.token()})
        self.assertContains(response, "cannot run this search", status_code=403)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")
        self.assertFalse(JobOutbox.objects.exists())

    def test_stale_confirmation_conflicts(self):
        data = {"confirmation": self.token()}
        Job.objects.filter(pk=self.job.pk).update(revision=1)
        self.assertContains(self.client.post(self.page, data), "job changed", status_code=409)
        self.assertFalse(JobOutbox.objects.exists())

    @override_settings(WEB_DASHBOARD_URL="http://localhost:3000/dashboard")
    def test_web_dashboard_redirects_with_notice(self):
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        response = self.client.post(self.page, {"confirmation": self.token()})
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.url.endswith(f"/jobs/{self.job.id}/submit?notice=limits"))

    def test_viewer_and_foreign_workspace_are_denied(self):
        other = User.objects.create_user(username="foreign-submit")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        foreign_job, _ = create_draft(other, foreign.id, self.job.search, "foreign-submit")
        self.assertEqual(
            self.client.get(f"/workspaces/{foreign.id}/jobs/{foreign_job.id}/submit/").status_code,
            404,
        )
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertNotContains(self.client.get(self.detail), "Submit job")
        self.assertEqual(self.client.get(self.page).status_code, 403)
        self.assertEqual(
            self.client.post(self.page, {"confirmation": self.token()}).status_code, 403
        )
        self.assertFalse(JobOutbox.objects.exists())

    def test_submit_form_context_requires_draft(self):
        self.client.cookies["csrftoken"] = "A" * 32
        url = f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/submit-form/"
        data = self.client.get(url).json()
        self.assertEqual((data["kind"], data["job"]["id"]), ("submit", str(self.job.id)))
        self.assertTrue(data["confirmation"])
        Job.objects.filter(pk=self.job.pk).update(status="queued")
        self.assertEqual(self.client.get(url).status_code, 400)
