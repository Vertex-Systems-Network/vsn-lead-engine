from unittest.mock import patch

from django.core import signing
from django.test import Client, TestCase

from .attempts import claim_pre_dispatch
from .cancellation_forms import TOKEN_SALT, cancellation_token
from .jobs import cancel_pending_job, enqueue_job
from .models import Job, JobAttempt, JobOutbox, Membership, User
from .services import create_draft, create_workspace
from .test_jobs import fixture


class CancellationWebTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        self.client.force_login(self.user)
        self.detail = f"/workspaces/{self.workspace.id}/jobs/{self.job.id}/"
        self.page = f"{self.detail}cancel/"

    def token(self):
        self.job.refresh_from_db()
        return cancellation_token(self.user, self.workspace.id, self.job)

    def test_draft_confirmation_get_is_read_only_and_post_replays(self):
        self.assertContains(self.client.get(self.detail), "Review cancellation")
        response = self.client.get(self.page)
        self.assertContains(response, "Confirm cancellation")
        self.assertContains(response, "does not delete the saved request or refund settled usage")
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("draft", 0))
        data = {"confirmation": response.context["form"].initial["confirmation"]}
        first = self.client.post(self.page, data)
        self.assertEqual(first.status_code, 303)
        self.assertEqual(first.url, self.detail)
        self.assertEqual(self.client.post(self.page, data).status_code, 303)
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("cancelled", 1))
        self.assertEqual(Job.objects.count(), 1)
        self.assertNotContains(self.client.get(self.detail), "Review cancellation")
        self.assertEqual(self.client.get(self.page).status_code, 409)

    def test_queued_cancellation_releases_once_and_invalidates_active_lease(self):
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        outbox = JobOutbox.objects.get(job=self.job)
        claim_pre_dispatch(outbox.id)
        data = {"confirmation": self.token()}
        self.assertEqual(self.client.post(self.page, data).status_code, 303)
        self.assertEqual(self.client.post(self.page, data).status_code, 303)
        self.job.refresh_from_db()
        outbox.refresh_from_db()
        outbox.reservation.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("cancelled", 2))
        self.assertEqual(outbox.status, "cancelled")
        self.assertEqual(outbox.reservation.status, "released")
        self.assertEqual(JobAttempt.objects.get(outbox=outbox).status, "cancelled")

    def test_stale_confirmation_and_running_or_finished_states_do_not_mutate(self):
        data = {"confirmation": self.token()}
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        response = self.client.post(self.page, data)
        self.assertContains(response, "The job changed", status_code=409)
        self.assertNotContains(response, "Confirm cancellation", status_code=409)
        outbox = JobOutbox.objects.get(job=self.job)
        for state in ("running", "partial", "completed", "failed", "paused"):
            Job.objects.filter(pk=self.job.id).update(status=state)
            self.assertEqual(self.client.get(self.page).status_code, 409)
            self.assertEqual(
                self.client.post(self.page, {"confirmation": self.token()}).status_code, 409
            )
            self.assertNotContains(self.client.get(self.detail), "Review cancellation")
        outbox.reservation.refresh_from_db()
        self.assertEqual(outbox.reservation.status, "reserved")

    def test_role_tenant_login_and_revoked_access(self):
        other = User.objects.create_user(username="foreign-cancel")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        foreign_job, _ = create_draft(other, foreign.id, self.job.search, "foreign")
        self.assertEqual(
            self.client.get(f"/workspaces/{foreign.id}/jobs/{foreign_job.id}/cancel/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/workspaces/{self.workspace.id}/jobs/{foreign_job.id}/cancel/", {}
            ).status_code,
            404,
        )
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertNotContains(self.client.get(self.detail), "Review cancellation")
        self.assertEqual(self.client.get(self.page).status_code, 403)
        self.assertEqual(
            self.client.post(self.page, {"confirmation": self.token()}).status_code, 403
        )
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")

    def test_invalid_expired_or_wrong_context_confirmation(self):
        second, _ = create_draft(self.user, self.workspace.id, self.job.search, "second")
        other = User.objects.create_user(username="other-cancel")
        with patch("django.core.signing.time.time", return_value=0):
            expired = self.token()
        bool_revision = signing.dumps(
            {
                "user": str(self.user.pk),
                "workspace": str(self.workspace.id),
                "job": str(self.job.pk),
                "revision": True,
            },
            salt=TOKEN_SALT,
        )
        for token in (
            "",
            "bad",
            self.token() + "x",
            expired,
            signing.dumps([], salt=TOKEN_SALT),
            cancellation_token(other, self.workspace.id, self.job),
            cancellation_token(self.user, self.workspace.id, second),
            bool_revision,
        ):
            self.assertEqual(self.client.post(self.page, {"confirmation": token}).status_code, 400)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")

    def test_membership_change_after_confirmation_is_checked_transactionally(self):
        def downgrade_then_cancel(*args, **kwargs):
            Membership.objects.filter(user=self.user, workspace=self.workspace).update(
                role="viewer"
            )
            return cancel_pending_job(*args, **kwargs)

        with patch("core.jobs.cancel_pending_job", side_effect=downgrade_then_cancel):
            self.assertEqual(
                self.client.post(self.page, {"confirmation": self.token()}).status_code, 403
            )
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")

    def test_csrf_and_unsupported_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.get(self.page)
        data = {"confirmation": response.context["form"].initial["confirmation"]}
        self.assertEqual(client.post(self.page, data).status_code, 403)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.page, data).status_code, 303)
        for method in (self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(method(self.page).status_code, 405)
