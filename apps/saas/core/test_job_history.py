from unittest.mock import patch

from django.core import signing
from django.test import TestCase
from django.utils import timezone

from .job_history import CURSOR_SALT
from .models import Job, JobOutbox, Membership, User
from .serializers import SearchSerializer
from .services import create_draft, create_workspace


class JobHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="history")
        self.workspace = create_workspace(self.user, {"name": "A", "timezone": "UTC"})
        other = User.objects.create_user(username="foreign-history")
        self.foreign = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        serializer = SearchSerializer(data={"countries": ["US"], "categories": ["bakery"]})
        serializer.is_valid(raise_exception=True)
        self.search = serializer.validated_data
        self.job, _ = create_draft(self.user, self.workspace.id, self.search, "draft")
        self.foreign_job, _ = create_draft(other, self.foreign.id, self.search, "foreign")
        self.page = f"/workspaces/{self.workspace.id}/jobs/"
        self.detail = f"{self.page}{self.job.id}/"

    def test_login_membership_and_viewer_read_boundaries(self):
        self.assertEqual(self.client.get(self.page).status_code, 302)
        self.assertEqual(self.client.get(self.detail).status_code, 302)
        self.client.force_login(self.user)
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertContains(self.client.get(self.page), str(self.job.id))
        self.assertContains(self.client.get(self.detail), "Required fields")
        self.assertEqual(self.client.get(f"{self.page}{self.foreign_job.id}/").status_code, 404)
        foreign_page = f"/workspaces/{self.foreign.id}/jobs/"
        self.assertEqual(self.client.get(foreign_page).status_code, 404)
        self.assertEqual(self.client.get(f"{foreign_page}{self.foreign_job.id}/").status_code, 404)
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.assertEqual(self.client.get(self.detail).status_code, 404)

    def test_no_mutations_or_private_dispatch_metadata(self):
        self.client.force_login(self.user)
        for url in (self.page, self.detail):
            for method in (
                self.client.post,
                self.client.put,
                self.client.patch,
                self.client.delete,
            ):
                self.assertEqual(method(url).status_code, 405)
        detail = self.client.get(self.detail)
        self.assertNotContains(detail, self.job.request_hash)
        self.assertNotContains(detail, "fencing_token")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "draft")
        self.assertFalse(JobOutbox.objects.exists())

    def test_escaping_text_status_semantics_and_accessible_navigation(self):
        self.client.force_login(self.user)
        self.workspace.name = "<script>bad()</script>"
        self.workspace.save()
        self.job.search["categories"] = ["<img src=x onerror=bad()>"]
        self.job.status = "partial"
        self.job.result_count = 7
        self.job.save()
        for url in (self.page, self.detail):
            response = self.client.get(url)
            self.assertContains(response, "&lt;script&gt;bad()&lt;/script&gt;")
            self.assertContains(response, "&lt;img src=x onerror=bad()&gt;")
            self.assertNotContains(response, "<script>")
            self.assertNotContains(response, "<img ")
            self.assertContains(response, "Partial")
            self.assertContains(response, 'aria-label="Workspace"')
        self.assertContains(self.client.get(self.page), '<th scope="col">Recorded results</th>')
        self.assertContains(self.client.get(self.detail), "Recorded results: 7")
        self.assertContains(
            self.client.get(self.detail), "Requested limits are not achieved counts"
        )
        self.assertContains(self.client.get(self.detail), "Created (UTC)")
        self.assertContains(self.client.get("/"), "View jobs")

    def test_chronological_bounded_pagination_with_ties_and_new_insert(self):
        self.client.force_login(self.user)
        for n in range(30):
            create_draft(self.user, self.workspace.id, self.search, f"draft-{n}")
        # Tied timestamps force the UUID tie breaker; foreign jobs are never included.
        tied = timezone.now()
        Job.objects.filter(workspace=self.workspace).update(created_at=tied)
        expected = list(Job.objects.filter(workspace=self.workspace).order_by("-created_at", "-id"))
        first = self.client.get(self.page)
        self.assertEqual([j.id for j in first.context["jobs"]], [j.id for j in expected[:25]])
        self.assertContains(first, "Older jobs")
        new, _ = create_draft(self.user, self.workspace.id, self.search, "newer")
        second = self.client.get(self.page, {"after": first.context["next_cursor"]})
        self.assertEqual([j.id for j in second.context["jobs"]], [j.id for j in expected[25:]])
        self.assertIsNone(second.context["next_cursor"])
        self.assertNotContains(second, str(new.id))
        self.assertNotContains(first, str(self.foreign_job.id))
        self.assertNotContains(second, str(self.foreign_job.id))

    def test_bad_expired_or_cross_workspace_cursors_fail_safely(self):
        self.client.force_login(self.user)
        data = {
            "workspace": str(self.workspace.id),
            "created": self.job.created_at.isoformat(),
            "id": str(self.job.id),
        }
        valid = signing.dumps(data, salt=CURSOR_SALT)
        with patch("django.core.signing.time.time", return_value=0):
            expired = signing.dumps(data, salt=CURSOR_SALT)
        bad_shape = signing.dumps([], salt=CURSOR_SALT)
        naive = signing.dumps({**data, "created": "2026-01-01T00:00:00"}, salt=CURSOR_SALT)
        for cursor in ("", "bad", valid + "x", expired, bad_shape, naive, "x" * 1025):
            self.assertEqual(self.client.get(self.page, {"after": cursor}).status_code, 400)
        Membership.objects.create(workspace=self.foreign, user=self.user, role="viewer")
        foreign_page = f"/workspaces/{self.foreign.id}/jobs/"
        self.assertEqual(self.client.get(foreign_page, {"after": valid}).status_code, 400)
        Membership.objects.filter(workspace=self.foreign, user=self.user).delete()
        self.assertEqual(self.client.get(foreign_page, {"after": valid}).status_code, 404)

    def test_empty_page_and_unknown_job(self):
        self.client.force_login(self.user)
        self.job.delete()
        self.assertContains(self.client.get(self.page), "No jobs on this page")
        self.assertEqual(self.client.get(self.detail).status_code, 404)
