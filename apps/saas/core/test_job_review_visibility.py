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

    def test_unrelated_and_revoked_users_cannot_read_review_signal(self):
        job = queued_job(self.owner, self.workspace)
        self.client.force_login(self.other)
        denied = self.client.get(self.url(job))
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn(b"execution_review_required", denied.content)

        self.client.force_login(self.viewer)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        revoked = self.client.get(self.url(job))
        self.assertEqual(revoked.status_code, 404)
        self.assertNotIn(b"execution_review_required", revoked.content)

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
