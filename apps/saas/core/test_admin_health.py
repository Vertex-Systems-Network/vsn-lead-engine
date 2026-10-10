"""Tenant-scoped read-only admin operations counts; no actor or source secrets."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import (
    Job,
    JobOutbox,
    Membership,
    MembershipAudit,
    UsageReservation,
    User,
    WorkspaceInvitation,
)
from .services import create_workspace


class AdminOperationalHealthTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="health-admin-owner")
        self.admin = User.objects.create_user(username="health-admin-admin")
        self.viewer = User.objects.create_user(username="health-admin-viewer")
        self.foreign = User.objects.create_user(username="health-foreign-owner")
        self.target = User.objects.create_user(username="health-pending-target")
        self.workspace = create_workspace(
            self.owner, {"name": "Private health", "timezone": "UTC"}
        )
        self.foreign_workspace = create_workspace(
            self.foreign, {"name": "Foreign confidential marker", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.admin, role="admin")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.path = f"/workspaces/{self.workspace.id}/admin/health/"

    def seed(self):
        job = Job.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            status="queued",
            search={"countries": ["US"], "categories": ["Secret synthetic industry"]},
            idempotency_key="health-report-job",
            request_hash="a" * 64,
        )
        reservation = UsageReservation.objects.create(
            workspace=self.workspace,
            key="health-report-reservation",
            request_hash="a" * 64,
            leads=1,
            jobs=1,
            status="reserved",
        )
        JobOutbox.objects.create(
            job=job,
            reservation=reservation,
            submitted_by=self.owner,
            submitted_revision=0,
            source_snapshot=[],
            status="pending",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            target=self.target,
            created_by=self.owner,
            role="member",
            token_hash="f" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        Job.objects.create(
            workspace=self.foreign_workspace,
            created_by=self.foreign,
            status="failed",
            search={"countries": ["US"], "categories": ["Foreign private industry"]},
            idempotency_key="foreign-health-job",
            request_hash="b" * 64,
        )
        return job

    def test_owner_and_admin_get_redacted_accurate_counts_without_mutations(self):
        job = self.seed()
        before = {
            "jobs": Job.objects.count(),
            "outboxes": JobOutbox.objects.count(),
            "reservations": UsageReservation.objects.count(),
            "invites": WorkspaceInvitation.objects.count(),
            "audit": MembershipAudit.objects.count(),
        }
        for actor in (self.owner, self.admin):
            self.client.force_login(actor)
            page = self.client.get(self.path)
            self.assertEqual(page.status_code, 200)
            self.assertIn("no-store", page["Cache-Control"])
            self.assertContains(page, "Workspace operational health")
            self.assertContains(page, "Pending intents past expiry")
            self.assertContains(page, "Outstanding reserved usage intents")
            self.assertContains(page, "read-only")
            report = page.context["report"]
            self.assertTrue(report["advisory_only"])
            self.assertEqual(report["member_roles"], {
                "owner": 1, "admin": 1, "member": 0, "viewer": 1
            })
            self.assertEqual(report["invitations"], {
                "pending": 1, "accepted": 0, "revoked": 0, "expired": 0
            })
            self.assertEqual(report["jobs"]["queued"], 1)
            self.assertEqual(report["jobs"]["failed"], 0)
            self.assertEqual(report["outboxes"]["pending"], 1)
            self.assertEqual(report["expired_pending_outboxes"], 1)
            self.assertEqual(report["unknown_dispatch_operations"], 0)
            self.assertEqual(report["reserved_usage_intents"], 1)
            self.assertNotContains(page, str(job.pk))
            self.assertNotContains(page, "Secret synthetic industry")
            self.assertNotContains(page, "Foreign confidential marker")
            self.assertNotContains(page, "Foreign private industry")
            self.assertNotContains(page, "f" * 64)
        self.assertEqual(
            before,
            {
                "jobs": Job.objects.count(),
                "outboxes": JobOutbox.objects.count(),
                "reservations": UsageReservation.objects.count(),
                "invites": WorkspaceInvitation.objects.count(),
                "audit": MembershipAudit.objects.count(),
            },
        )

    def test_no_invites_or_jobs_stays_explicit_zero(self):
        self.client.force_login(self.owner)
        report = self.client.get(self.path).context["report"]
        self.assertEqual(sum(report["jobs"].values()), 0)
        self.assertEqual(sum(report["outboxes"].values()), 0)
        self.assertEqual(sum(report["invitations"].values()), 0)
        self.assertEqual(report["expired_pending_outboxes"], 0)
        self.assertEqual(report["unknown_dispatch_operations"], 0)

    def test_viewer_foreign_revoked_and_anonymous_are_denied(self):
        self.seed()
        self.assertEqual(self.client.get(self.path).status_code, 302)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.foreign_workspace.id}/admin/health/"
            ).status_code,
            200,
        )
        self.client.force_login(self.admin)
        Membership.objects.filter(workspace=self.workspace, user=self.admin).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_get_only_no_filters_or_mutations(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.path + "?workspace=all").status_code, 400)
        self.assertEqual(self.client.post(self.path, {}).status_code, 405)
        self.assertEqual(self.client.patch(self.path, {}).status_code, 405)
        self.assertEqual(self.client.delete(self.path).status_code, 405)
        self.assertFalse(Job.objects.exists())
