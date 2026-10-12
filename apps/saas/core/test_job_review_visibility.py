"""Tenant-scoped read-only customer visibility for held dispatch outcomes."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from .fulfilment import run_pending
from .models import DispatchOperation, Entitlement, JobOutbox, Membership, User
from .services import create_workspace
from .test_fulfilment import LOCAL, queued_job


@override_settings(**LOCAL)
class JobExecutionReviewVisibilityTests(TestCase):
    def setUp(self):
        call_command("seed_local_source", stdout=StringIO())
        self.owner = User.objects.create_user(username="review-visibility-owner")
        self.workspace = create_workspace(
            self.owner, {"name": "Review visibility", "timezone": "UTC"}
        )
        Entitlement.objects.create(
            workspace=self.workspace,
            active=True,
            lead_limit=100,
            job_limit=5,
            provider_call_limit=5,
        )
        self.viewer = User.objects.create_user(username="review-visibility-viewer")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.other = User.objects.create_user(username="review-visibility-other")
        self.foreign = create_workspace(
            self.other, {"name": "Foreign private space", "timezone": "UTC"}
        )

    def url(self, job):
        return f"/api/v1/workspaces/{job.workspace_id}/jobs/{job.id}/"

    def test_unknown_dispatch_is_explicitly_reported_without_leaking_ledger_details(self):
        job = queued_job(self.owner, self.workspace)
        self.client.force_login(self.owner)
        pending = self.client.get(self.url(job))
        self.assertEqual(pending.status_code, 200)
        self.assertIs(pending.json()["execution_review_required"], False)
        list_path = f"/api/v1/workspaces/{self.workspace.id}/jobs/"
        pending_list = self.client.get(list_path)
        self.assertEqual(pending_list.status_code, 200)
        self.assertIs(
            next(row for row in pending_list.json()["results"] if row["id"] == str(job.id))[
                "execution_review_required"
            ],
            False,
        )
        native_path = f"/workspaces/{self.workspace.id}/jobs/{job.id}/"
        self.assertContains(self.client.get(native_path), 'http-equiv="refresh"')

        secret = "private-provider-secret-must-not-be-exposed"
        with patch("core.sources.FixtureSource.fetch", side_effect=RuntimeError(secret)):
            self.assertEqual(run_pending(limit=1)["unknown"], 1)
        operation = DispatchOperation.objects.get(job=job)
        self.assertEqual(operation.status, "unknown")
        reservation = JobOutbox.objects.get(job=job).reservation
        self.assertEqual(reservation.status, "reserved")

        before = (
            operation.status,
            reservation.status,
            DispatchOperation.objects.filter(job=job).count(),
        )
        response = self.client.get(self.url(job))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIs(data["execution_review_required"], True)
        self.assertEqual(data["status"], "running")
        held_list = self.client.get(list_path)
        self.assertEqual(held_list.status_code, 200)
        held_row = next(row for row in held_list.json()["results"] if row["id"] == str(job.id))
        self.assertIs(held_row["execution_review_required"], True)
        self.assertEqual(held_row["status"], "running")
        self.assertNotIn(secret, held_list.content.decode())
        self.assertNotIn(str(operation.provider_key), held_list.content.decode())
        native = self.client.get(native_path)
        self.assertEqual(native.status_code, 200)
        self.assertContains(native, "needs authorized operator review")
        self.assertContains(native, 'role="status"')
        self.assertNotContains(native, 'http-equiv="refresh"')
        self.assertNotContains(native, "refreshes every 15 seconds")
        for forbidden in (
            secret,
            str(operation.id),
            str(operation.provider_key),
            str(reservation.id),
            "token",
            "unknown_at",
        ):
            self.assertNotIn(forbidden, response.content.decode())
        operation.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(
            (
                operation.status,
                reservation.status,
                DispatchOperation.objects.filter(job=job).count(),
            ),
            before,
        )

        self.client.force_login(self.viewer)
        viewer = self.client.get(self.url(job))
        self.assertEqual(viewer.status_code, 200)
        self.assertIs(viewer.json()["execution_review_required"], True)
        viewer_list = self.client.get(list_path)
        self.assertEqual(viewer_list.status_code, 200)
        self.assertTrue(
            any(
                row["id"] == str(job.id) and row["execution_review_required"] is True
                for row in viewer_list.json()["results"]
            )
        )
        viewer_native = self.client.get(native_path)
        self.assertContains(viewer_native, "needs authorized operator review")
        self.assertNotContains(viewer_native, 'http-equiv="refresh"')
        self.assertNotContains(viewer_native, str(operation.provider_key))

    def test_unrelated_and_revoked_users_cannot_read_review_signal(self):
        job = queued_job(self.owner, self.workspace)
        self.client.force_login(self.other)
        denied = self.client.get(self.url(job))
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn(b"execution_review_required", denied.content)
        native_path = f"/workspaces/{self.workspace.id}/jobs/{job.id}/"
        self.assertEqual(self.client.get(native_path).status_code, 404)

        self.client.force_login(self.viewer)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        revoked = self.client.get(self.url(job))
        self.assertEqual(revoked.status_code, 404)
        self.assertNotIn(b"execution_review_required", revoked.content)
        self.assertEqual(self.client.get(native_path).status_code, 404)

    def test_healthy_completion_and_foreign_unknown_do_not_trigger_review(self):
        blocked = queued_job(self.owner, self.workspace)
        with patch("core.sources.FixtureSource.fetch", side_effect=RuntimeError("private")):
            self.assertEqual(run_pending(limit=1)["unknown"], 1)
        self.assertEqual(DispatchOperation.objects.get(job=blocked).status, "unknown")

        Entitlement.objects.create(
            workspace=self.foreign,
            active=True,
            lead_limit=100,
            job_limit=5,
            provider_call_limit=5,
        )
        healthy = queued_job(self.other, self.foreign)
        self.assertEqual(run_pending(limit=1)["completed"], 1)
        self.client.force_login(self.other)
        response = self.client.get(self.url(healthy))
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["execution_review_required"], False)
        self.assertEqual(response.json()["status"], "completed")
