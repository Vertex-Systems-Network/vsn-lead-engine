from unittest.mock import patch

from django.core import signing
from django.test import Client, TestCase

from .forms import TOKEN_SALT, new_draft_token
from .models import Job, JobOutbox, Membership, UsageReservation, User
from .services import create_draft, create_workspace


class DraftWebTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="draft-web")
        self.workspace = create_workspace(self.user, {"name": "A", "timezone": "UTC"})
        self.page = f"/workspaces/{self.workspace.id}/search/new/"
        self.client.force_login(self.user)

    def data(self, **overrides):
        return {
            "countries": ["CA", "US"],
            "categories": "bakery\n bakery\nflorist",
            "result_limit": "50",
            "draft_token": new_draft_token(self.user, self.workspace.id),
            **overrides,
        }

    def test_saves_normalized_draft_and_redirects_without_reservation_or_dispatch(self):
        get = self.client.get(self.page)
        self.assertEqual(get.status_code, 200)
        token = get.context["form"].initial["draft_token"]
        response = self.client.post(self.page, self.data(draft_token=token))
        self.assertEqual(response.status_code, 303)
        job = Job.objects.get()
        self.assertEqual(response.url, f"/workspaces/{self.workspace.id}/jobs/{job.id}/")
        self.assertEqual(job.created_by, self.user)
        self.assertEqual(job.search["countries"], ["CA", "US"])
        self.assertEqual(job.search["categories"], ["bakery", "florist"])
        self.assertEqual(job.search["required_fields"], ["phone"])
        self.assertEqual(job.status, "draft")
        self.assertEqual(job.result_count, 0)
        self.assertFalse(JobOutbox.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())

    def test_same_submission_replays_and_changed_submission_conflicts(self):
        data = self.data()
        first = self.client.post(self.page, data)
        second = self.client.post(self.page, data)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(first.url, second.url)
        response = self.client.post(self.page, {**data, "result_limit": "51"})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "already saved a different search", status_code=409)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(Job.objects.get().search["result_limit"], 50)

    def test_field_errors_preserve_values_and_allow_correction_with_same_token(self):
        data = self.data(countries=["GB"], categories="<script>bad()</script>", result_limit="1001")
        response = self.client.post(self.page, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context["form"]["categories"].value(), data["categories"])
        self.assertContains(response, "&lt;script&gt;bad()&lt;/script&gt;", status_code=400)
        self.assertNotContains(response, "<script>", status_code=400)
        self.assertContains(response, 'href="#field_countries"', status_code=400)
        self.assertContains(response, 'role="alert"', status_code=400)
        self.assertFalse(Job.objects.exists())
        response = self.client.post(self.page, {**data, "countries": ["US"], "result_limit": "100"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(Job.objects.count(), 1)

    def test_serializer_contract_limits_and_unknown_choices(self):
        for data in (
            self.data(categories="\n".join(f"category-{n}" for n in range(13))),
            self.data(categories="x" * 121),
            self.data(categories="\n  \n"),
            self.data(source_codes="x" * 65),
            self.data(source_codes="\n".join(f"source-{n}" for n in range(13))),
            self.data(statuses=["invented"]),
            self.data(required_fields=["secret"]),
        ):
            self.assertEqual(self.client.post(self.page, data).status_code, 400)
        self.assertFalse(Job.objects.exists())

    def test_membership_roles_and_transactional_recheck(self):
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(self.page, self.data()).status_code, 403)
        self.assertNotContains(
            self.client.get(f"/workspaces/{self.workspace.id}/jobs/"), "Save a search draft"
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="member")

        def revoke_then_save(*args, **kwargs):
            Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
            return create_draft(*args, **kwargs)

        with patch("core.views.create_draft", side_effect=revoke_then_save):
            self.assertEqual(self.client.post(self.page, self.data()).status_code, 404)
        self.assertFalse(Job.objects.exists())
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 302)

    def test_token_tampering_expiry_and_actor_workspace_binding(self):
        other = User.objects.create_user(username="other-draft")
        foreign = create_workspace(other, {"name": "Foreign", "timezone": "UTC"})
        with patch("django.core.signing.time.time", return_value=0):
            expired = new_draft_token(self.user, self.workspace.id)
        malformed = signing.dumps([], salt=TOKEN_SALT)
        for token in (
            "",
            "bad",
            self.data()["draft_token"] + "x",
            expired,
            malformed,
            new_draft_token(other, self.workspace.id),
            new_draft_token(self.user, foreign.id),
        ):
            self.assertEqual(
                self.client.post(self.page, self.data(draft_token=token)).status_code, 400
            )
        self.assertFalse(Job.objects.exists())
        self.assertEqual(
            self.client.post(f"/workspaces/{foreign.id}/search/new/", self.data()).status_code, 404
        )

    def test_csrf_protection_and_method_rejection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        get = client.get(self.page)
        data = self.data(draft_token=get.context["form"].initial["draft_token"])
        self.assertEqual(client.post(self.page, data).status_code, 403)
        self.assertFalse(Job.objects.exists())
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.page, data).status_code, 303)
        for method in (self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(method(self.page).status_code, 405)
