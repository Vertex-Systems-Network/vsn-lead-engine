from django.test import Client, TestCase, override_settings

from .models import Job, JobOutbox, Membership, UsageReservation, User
from .services import create_workspace
from .test_jobs import fixture


@override_settings(
    WEB_DASHBOARD_URL="http://localhost:3000/dashboard",
    CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
)
class FormContextTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.draft = f"/api/v1/workspaces/{self.workspace.id}/draft-form/"
        self.cancel = f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/cancel-form/"
        self.submit = f"/workspaces/{self.workspace.id}/search/new/"
        self.cancel_submit = f"/workspaces/{self.workspace.id}/jobs/{self.job.id}/cancel/"
        self.client.get("/accounts/check-session/")

    def payload(self, context):
        return {
            "countries": ["US", "CA"],
            "categories": "Native bakery",
            "result_limit": "5",
            "draft_token": context["draft_token"],
            "csrfmiddlewaretoken": context["csrf_token"],
        }

    def test_private_readonly_context_requires_cookie_and_reseeding_does_not_create_jobs(self):
        self.client.cookies.pop("csrftoken")
        self.assertEqual(self.client.get(self.draft).status_code, 403)
        response = self.client.get("/accounts/check-session/")
        self.assertContains(response, "Session ready")
        self.assertIn("csrftoken", response.cookies)
        response = self.client.get(self.draft)
        data = response.json()
        self.assertEqual(data["kind"], "draft")
        self.assertEqual(data["workspace"]["id"], str(self.workspace.id))
        self.assertEqual(len(data["csrf_token"]), 64)
        self.assertNotEqual(data["csrf_token"], self.client.cookies["csrftoken"].value)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())
        self.assertEqual(
            self.client.post(
                self.draft,
                "{}",
                content_type="application/json",
                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
            ).status_code,
            405,
        )

    def test_exact_frontend_origin_draft_saves_once_and_returns_only_fixed_next_job_path(self):
        data = self.payload(self.client.get(self.draft).json())
        first = self.client.post(self.submit, data, HTTP_ORIGIN="http://localhost:3000")
        self.assertEqual(first.status_code, 303)
        job = Job.objects.get(search__categories=["Native bakery"])
        self.assertEqual(
            first.url,
            f"http://localhost:3000/dashboard/workspaces/{self.workspace.id}/jobs/{job.id}",
        )
        self.assertEqual(job.search["required_fields"], ["phone"])
        self.assertEqual(
            self.client.post(self.submit, data, HTTP_ORIGIN="http://localhost:3000").url, first.url
        )
        self.assertEqual(
            self.client.post(
                self.submit, {**data, "result_limit": "6"}, HTTP_ORIGIN="http://localhost:3000"
            ).status_code,
            303,
        )
        self.assertEqual(Job.objects.count(), 2)
        self.assertFalse(UsageReservation.objects.exists())
        self.assertFalse(JobOutbox.objects.exists())

    def test_untrusted_origin_missing_mismatched_and_rotated_csrf_block_native_submission(self):
        data = self.payload(self.client.get(self.draft).json())
        for origin in [
            "http://localhost:3999",
            "https://evil.example.test",
            "http://sub.localhost:3000",
        ]:
            self.assertEqual(
                self.client.post(self.submit, data, HTTP_ORIGIN=origin).status_code, 403
            )
        self.assertEqual(
            self.client.post(
                self.submit,
                {**data, "csrfmiddlewaretoken": ""},
                HTTP_ORIGIN="http://localhost:3000",
            ).status_code,
            403,
        )
        self.client.cookies["csrftoken"] = "B" * 32
        self.assertEqual(
            self.client.post(self.submit, data, HTTP_ORIGIN="http://localhost:3000").status_code,
            403,
        )
        self.assertEqual(Job.objects.count(), 1)

    def test_viewer_revocation_foreign_context_and_foreign_confirmation_cannot_mutate(self):
        data = self.payload(self.client.get(self.draft).json())
        other = User.objects.create_user(username="context-other")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        self.assertEqual(
            self.client.get(f"/api/v1/workspaces/{foreign.id}/draft-form/").status_code, 404
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/workspaces/{foreign.id}/jobs/{self.job.id}/cancel-form/"
            ).status_code,
            404,
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        for endpoint in [self.draft, self.cancel]:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.assertEqual(
            self.client.post(self.submit, data, HTTP_ORIGIN="http://localhost:3000").status_code,
            403,
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.draft).status_code, 404)
        self.assertEqual(
            self.client.post(self.submit, data, HTTP_ORIGIN="http://localhost:3000").status_code,
            404,
        )
        self.assertEqual(Job.objects.count(), 1)

    def test_cancel_context_is_bound_to_pending_revision_and_replays_safe_cancellation(self):
        context = self.client.get(self.cancel).json()
        data = {
            "confirmation": context["confirmation"],
            "csrfmiddlewaretoken": context["csrf_token"],
        }
        self.assertEqual(context["job"]["id"], str(self.job.id))
        response = self.client.post(self.cancel_submit, data, HTTP_ORIGIN="http://localhost:3000")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.url,
            f"http://localhost:3000/dashboard/workspaces/{self.workspace.id}/jobs/{self.job.id}",
        )
        self.assertEqual(
            self.client.post(
                self.cancel_submit, data, HTTP_ORIGIN="http://localhost:3000"
            ).status_code,
            303,
        )
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("cancelled", 1))
        self.assertEqual(self.client.get(self.cancel).status_code, 400)

    def test_stale_cancel_context_or_running_state_is_not_authority(self):
        context = self.client.get(self.cancel).json()
        data = {
            "confirmation": context["confirmation"],
            "csrfmiddlewaretoken": context["csrf_token"],
        }
        Job.objects.filter(pk=self.job.id).update(revision=1)
        self.assertEqual(
            self.client.post(
                self.cancel_submit, data, HTTP_ORIGIN="http://localhost:3000"
            ).status_code,
            409,
        )
        Job.objects.filter(pk=self.job.id).update(status="running")
        self.assertEqual(self.client.get(self.cancel).status_code, 400)
        self.assertEqual(
            self.client.post(
                self.cancel_submit, data, HTTP_ORIGIN="http://localhost:3000"
            ).status_code,
            409,
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "running")

    def test_new_actor_cannot_reuse_previous_actors_draft_token(self):
        old = self.client.get(self.draft).json()
        other = User.objects.create_user(username="context-member")
        Membership.objects.create(workspace=self.workspace, user=other, role="member")
        self.client.force_login(other)
        self.client.get("/accounts/check-session/")
        fresh = self.client.get(self.draft).json()
        self.assertEqual(
            self.client.post(
                self.submit,
                self.payload({**old, "csrf_token": fresh["csrf_token"]}),
                HTTP_ORIGIN="http://localhost:3000",
            ).status_code,
            400,
        )
        self.assertEqual(Job.objects.count(), 1)

    def test_anonymous_context_and_reseed_are_protected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.draft).status_code, 403)
        self.assertEqual(self.client.get(self.cancel).status_code, 403)
        self.assertEqual(self.client.get("/accounts/check-session/").status_code, 302)
