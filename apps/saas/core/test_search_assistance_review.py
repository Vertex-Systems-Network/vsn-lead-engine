"""One-time review handoff is not a job submission or AI/provider dispatch."""

from unittest.mock import patch

from django.test import Client, TestCase

from .models import Job, JobOutbox, Membership, UsageReservation, User
from .services import create_workspace


class ReviewedSuggestionHandoffTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="assist-review-owner")
        self.member = User.objects.create_user(username="assist-review-member")
        self.viewer = User.objects.create_user(username="assist-review-viewer")
        self.foreign_owner = User.objects.create_user(username="assist-review-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Reviewed private workspace", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_owner, {"name": "Foreign review secret", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.member, role="member")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.preview_path = f"/workspaces/{self.workspace.pk}/search-assistance/"
        self.review_path = f"/workspaces/{self.workspace.pk}/search-assistance/review/"
        self.draft_path = f"/workspaces/{self.workspace.pk}/search/new/"
        self.client = Client(enforce_csrf_checks=True)

    def preview(self, actor=None, intent="US salons and Canada spas"):
        self.client.force_login(actor or self.owner)
        self.assertEqual(self.client.get(self.preview_path).status_code, 200)
        response = self.client.post(
            self.preview_path,
            {
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                "intent": intent,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response

    def handoff(self, token, *, actor=None):
        self.client.force_login(actor or self.owner)
        return self.client.post(
            self.review_path,
            {
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                "review_token": token,
            },
        )

    def test_proposal_only_appears_for_safe_complete_request_and_no_write_until_save(self):
        response = self.preview()
        token = response.context["review_token"]
        self.assertIsInstance(token, str)
        self.assertNotIn("US salons and Canada spas", token)
        self.assertContains(response, "Review suggested options in a draft form")
        review = self.handoff(token)
        self.assertEqual(review.status_code, 200)
        self.assertIn("no-store", review["Cache-Control"])
        self.assertContains(review, "No draft has been created")
        self.assertContains(review, "Save reviewed draft")
        self.assertContains(
            review, f'action="{self.draft_path}"'
        )
        form = review.context["form"]
        self.assertEqual(form.initial["countries"], ["CA", "US"])
        self.assertEqual(form.initial["categories"], "salon\nspa")
        self.assertEqual(form.initial["statuses"], [])
        self.assertEqual(form.initial["source_codes"], "")
        self.assertEqual(form.initial["result_limit"], 25)
        self.assertFalse(Job.objects.exists())
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())
        data = {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "draft_token": form["draft_token"].value(),
            "countries": form.initial["countries"],
            "categories": form.initial["categories"],
            "result_limit": "25",
        }
        saved = self.client.post(self.draft_path, data)
        self.assertEqual(saved.status_code, 303)
        job = Job.objects.get()
        self.assertEqual(job.search["countries"], ["CA", "US"])
        self.assertEqual(job.search["categories"], ["salon", "spa"])
        self.assertEqual(job.search["result_limit"], 25)
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())

    def test_incomplete_preview_offers_no_review_token(self):
        response = self.preview(intent="US salons except spas")
        self.assertIsNone(response.context["review_token"])
        self.assertNotContains(response, "Review suggested options in a draft form")
        self.assertFalse(Job.objects.exists())

    def test_expired_tampered_and_foreign_actor_review_fail_closed(self):
        response = self.preview()
        token = response.context["review_token"]
        self.assertEqual(self.handoff(token[:-1] + ("x" if token[-1] != "x" else "y")).status_code, 400)
        self.assertEqual(self.handoff(token, actor=self.member).status_code, 400)
        with patch("django.core.signing.time.time", return_value=0):
            expired = self.preview().context["review_token"]
        self.assertEqual(self.handoff(expired).status_code, 400)
        self.assertFalse(Job.objects.exists())

    def test_replay_only_opens_editable_review_and_never_saves(self):
        token = self.preview().context["review_token"]
        self.assertEqual(self.handoff(token).status_code, 200)
        self.assertEqual(self.handoff(token).status_code, 200)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(JobOutbox.objects.count(), 0)

    def test_viewer_foreign_revoked_and_unsupported_methods(self):
        token = self.preview().context["review_token"]
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(
            self.review_path,
            {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value, "review_token": token},
        ).status_code, 403)
        self.client.force_login(self.foreign_owner)
        self.assertEqual(self.client.post(
            self.review_path,
            {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value, "review_token": token},
        ).status_code, 404)
        self.client.force_login(self.owner)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.handoff(token).status_code, 404)

    def test_no_get_csrf_bypass_query_or_unapproved_extra_fields(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.review_path).status_code, 405)
        self.assertEqual(
            self.client.post(self.review_path, {"review_token": "forged"}).status_code, 403
        )
        token = self.preview().context["review_token"]
        csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(
            self.client.post(
                self.review_path + "?intent=US",
                {"csrfmiddlewaretoken": csrf, "review_token": token},
            ).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                self.review_path,
                {"csrfmiddlewaretoken": csrf, "review_token": token, "execute": "yes"},
            ).status_code, 400
        )
        self.assertFalse(Job.objects.exists())
