"""Read-only job counts must be exact, scoped, stable and safe for viewers."""

from django.test import TestCase

from .job_query import JOB_STATES
from .models import Job, Membership, User
from .services import create_workspace


class JobStatusSummaryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="job-summary-owner")
        self.viewer = User.objects.create_user(username="job-summary-viewer")
        self.other = User.objects.create_user(username="job-summary-other")
        self.workspace = create_workspace(
            self.owner, {"name": "Confidential summary", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign workspace private", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.path = f"/api/v1/workspaces/{self.workspace.id}/job-summary/"

    def job(self, workspace, key, state):
        return Job.objects.create(
            workspace=workspace,
            created_by=self.owner if workspace == self.workspace else self.other,
            search={"countries": ["US"], "categories": ["Synthetic only"]},
            status=state,
            idempotency_key=key,
            request_hash="a" * 64,
        )

    def test_empty_workspace_has_all_explicit_zero_states(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "workspace_id": str(self.workspace.id),
                "total": 0,
                "statuses": dict.fromkeys(JOB_STATES, 0),
            },
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_counts_all_states_not_only_first_page_or_foreign_jobs(self):
        for n in range(29):
            self.job(self.workspace, f"draft-{n}", "draft")
        self.job(self.workspace, "running-job", "running")
        self.job(self.workspace, "finished-job", "completed")
        self.job(self.foreign, "foreign-job", "failed")
        self.client.force_login(self.viewer)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 31)
        statuses = response.json()["statuses"]
        self.assertEqual(statuses["draft"], 29)
        self.assertEqual(statuses["running"], 1)
        self.assertEqual(statuses["completed"], 1)
        self.assertEqual(statuses["failed"], 0)
        self.assertEqual(set(statuses), set(JOB_STATES))
        self.assertNotIn(b"Foreign workspace private", response.content)
        self.assertNotIn(b"Synthetic only", response.content)
        self.assertNotIn(b"Confidential summary", response.content)

    def test_anonymous_foreign_and_revoked_access_are_denied(self):
        self.job(self.workspace, "secret-job", "completed")
        anonymous = self.client.get(self.path)
        self.assertIn(anonymous.status_code, (401, 403))
        self.assertNotIn(b"completed", anonymous.content)
        self.client.force_login(self.other)
        foreign = self.client.get(self.path)
        self.assertEqual(foreign.status_code, 404)
        self.assertNotIn(b"completed", foreign.content)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_no_query_filter_or_write_verbs(self):
        self.client.force_login(self.owner)
        for query in ("?status=completed", "?after=cursor", "?unused=1"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.path + query).status_code, 400)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.path).status_code, 405)
        self.assertFalse(Job.objects.exists())
