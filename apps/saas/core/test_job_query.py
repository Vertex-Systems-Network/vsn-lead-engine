from django.test import TestCase

from .models import Job, Membership, User
from .services import create_workspace
from .test_jobs import fixture


class JobQueryTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        self.client.force_login(self.user)
        self.url = f"/api/v1/workspaces/{self.workspace.id}/jobs/"

    def test_state_filter_bounded_cursor_continuation_and_no_other_state(self):
        Job.objects.bulk_create(
            [
                Job(
                    workspace=self.workspace,
                    created_by=self.user,
                    search=self.job.search,
                    idempotency_key=f"query-{n}",
                    request_hash="a" * 64,
                    status="cancelled" if n < 27 else "draft",
                )
                for n in range(30)
            ]
        )
        page = self.client.get(self.url, {"status": "cancelled"}).json()
        self.assertEqual(len(page["results"]), 25)
        self.assertTrue(all(j["status"] == "cancelled" for j in page["results"]))
        second = self.client.get(self.url, {"status": "cancelled", "after": page["next"]}).json()
        self.assertEqual(len(second["results"]), 2)
        self.assertIsNone(second["next"])
        self.assertTrue(
            {j["id"] for j in page["results"]}.isdisjoint({j["id"] for j in second["results"]})
        )
        self.assertEqual(len(self.client.get(self.url, {"status": "draft"}).json()["results"]), 4)
        self.assertEqual(
            self.client.get(self.url, {"status": "queued"}).json(), {"results": [], "next": None}
        )

    def test_invalid_repeated_unknown_and_unbounded_query_are_rejected(self):
        for query in [
            "status=unknown",
            "status=",
            "status=draft&status=cancelled",
            "after=x",
            "after=",
            "after=x&after=y",
            "target=https://evil.test",
            "page=1000000",
            "status=" + "x" * 1000,
        ]:
            self.assertEqual(self.client.get(self.url + "?" + query).status_code, 400)

    def test_filter_is_tenant_scoped_with_foreign_cursor_and_membership_recheck(self):
        other = User.objects.create_user(username="query-other")
        workspace = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        foreign = Job.objects.create(
            workspace=workspace,
            created_by=other,
            search=self.job.search,
            idempotency_key="other",
            request_hash="b" * 64,
        )
        page = self.client.get(self.url, {"status": "draft", "after": str(foreign.id)}).json()
        self.assertTrue(all(j["workspace_id"] == str(self.workspace.id) for j in page["results"]))
        self.assertEqual(
            self.client.get(
                f"/api/v1/workspaces/{workspace.id}/jobs/", {"status": "draft"}
            ).status_code,
            404,
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(self.url, {"status": "draft"}).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.url, {"status": "draft"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"status": "draft"}).status_code, 403)

    def test_every_supported_state_is_read_only_and_unknown_query_does_not_change_a_job(self):
        from .job_query import JOB_STATES

        for state in JOB_STATES:
            response = self.client.get(self.url, {"status": state})
            self.assertEqual(response.status_code, 200)
            self.assertIn("private", response["Cache-Control"])
            self.assertIn("no-store", response["Cache-Control"])
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.revision), ("draft", 0))
