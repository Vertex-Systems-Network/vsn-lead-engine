"""Tenant-scoped read-only admin operations counts; no actor or source secrets."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import (
    DispatchOperation,
    Job,
    JobAttempt,
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
        self.workspace = create_workspace(self.owner, {"name": "Private health", "timezone": "UTC"})
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
            self.assertEqual(
                report["member_roles"], {"owner": 1, "admin": 1, "member": 0, "viewer": 1}
            )
            self.assertEqual(
                report["invitations"], {"pending": 1, "accepted": 0, "revoked": 0, "expired": 0}
            )
            self.assertEqual(report["jobs"]["queued"], 1)
            self.assertEqual(report["jobs"]["failed"], 0)
            self.assertEqual(report["outboxes"]["pending"], 1)
            self.assertEqual(report["expired_pending_outboxes"], 1)
            self.assertEqual(report["pending_possible_effect_intents"], 0)
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

    def test_json_snapshot_matches_tenant_counts_without_exposing_private_rows(self):
        self.seed()
        api_path = f"/api/v1/workspaces/{self.workspace.id}/admin/health/"
        for actor in (self.owner, self.admin):
            self.client.force_login(actor)
            response = self.client.get(api_path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["Content-Type"], "application/json")
            report = response.json()
            self.assertEqual(report["workspace_id"], str(self.workspace.id))
            self.assertTrue(report["advisory_only"])
            self.assertEqual(
                report["member_roles"], {"owner": 1, "admin": 1, "member": 0, "viewer": 1}
            )
            self.assertEqual(report["invitations"]["pending"], 1)
            self.assertEqual(report["jobs"]["queued"], 1)
            self.assertEqual(report["jobs"]["failed"], 0)
            self.assertEqual(report["outboxes"]["pending"], 1)
            self.assertEqual(report["expired_pending_outboxes"], 1)
            self.assertEqual(report["reserved_usage_intents"], 1)
            body = response.content.decode()
            for forbidden in (
                "Private health",
                "Secret synthetic industry",
                "Foreign confidential marker",
                "Foreign private industry",
                "health-report-reservation",
                "f" * 64,
            ):
                self.assertNotIn(forbidden, body)
        self.assertEqual(Job.objects.count(), 2)
        self.assertEqual(JobOutbox.objects.count(), 1)
        self.assertEqual(UsageReservation.objects.count(), 1)
        self.assertEqual(WorkspaceInvitation.objects.count(), 1)

    def test_json_snapshot_rejects_anonymous_viewer_foreign_queries_and_writes(self):
        api_path = f"/api/v1/workspaces/{self.workspace.id}/admin/health/"
        self.assertIn(self.client.get(api_path).status_code, (401, 403))
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(api_path).status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(api_path).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(api_path + "?all=true").status_code, 400)
        self.assertEqual(self.client.post(api_path, {}).status_code, 405)
        self.assertEqual(self.client.patch(api_path, {}).status_code, 405)
        self.assertEqual(self.client.delete(api_path).status_code, 405)
        self.assertEqual(self.client.get(api_path).json()["jobs"]["queued"], 0)
        self.assertFalse(Job.objects.exists())

    def test_pre_dispatch_lease_counts_stay_tenant_scoped_and_read_only(self):
        job = self.seed()
        outbox = JobOutbox.objects.get(job=job)
        now = timezone.now()
        active = JobAttempt.objects.create(
            outbox=outbox,
            number=1,
            job_revision=0,
            status="leased",
            expires_at=now + timedelta(minutes=2),
        )
        JobAttempt.objects.create(
            outbox=outbox,
            number=2,
            job_revision=0,
            status="expired",
            expires_at=now - timedelta(minutes=1),
        )
        JobAttempt.objects.create(
            outbox=outbox,
            number=3,
            job_revision=0,
            status="done",
            expires_at=now - timedelta(minutes=1),
        )
        foreign_job = Job.objects.get(workspace=self.foreign_workspace)
        foreign_reservation = UsageReservation.objects.create(
            workspace=self.foreign_workspace,
            key="foreign-secret-lease-reservation",
            request_hash="b" * 64,
            leads=1,
            jobs=1,
            status="reserved",
        )
        foreign_outbox = JobOutbox.objects.create(
            job=foreign_job,
            reservation=foreign_reservation,
            submitted_by=self.foreign,
            submitted_revision=0,
            source_snapshot=[],
            status="pending",
        )
        foreign_attempt = JobAttempt.objects.create(
            outbox=foreign_outbox,
            number=1,
            job_revision=0,
            status="cancelled",
            expires_at=now - timedelta(minutes=1),
        )
        snapshot_api = f"/api/v1/workspaces/{self.workspace.id}/admin/health/"
        for actor in (self.owner, self.admin):
            self.client.force_login(actor)
            response = self.client.get(snapshot_api)
            self.assertEqual(response.status_code, 200)
            report = response.json()
            self.assertEqual(
                report["pre_dispatch_attempts"],
                {"leased": 1, "expired": 1, "cancelled": 0, "started": 0, "done": 1},
            )
            self.assertEqual(report["expired_leased_attempts"], 0)
            self.assertEqual(report["pending_possible_effect_intents"], 1)
            self.assertNotIn(str(active.token), response.content.decode())
            self.assertNotIn(str(foreign_attempt.pk), response.content.decode())
            self.assertNotIn("foreign-secret-lease-reservation", response.content.decode())
            page = self.client.get(self.path)
            self.assertContains(page, "Pre-dispatch lease attempts")
            self.assertContains(page, "Leases past expiry, still recorded as leased")

        JobAttempt.objects.filter(pk=active.pk).update(expires_at=now - timedelta(seconds=1))
        self.client.force_login(self.owner)
        response = self.client.get(snapshot_api)
        self.assertEqual(response.json()["expired_leased_attempts"], 1)
        self.assertEqual(response.json()["pre_dispatch_attempts"]["leased"], 1)
        self.assertEqual(JobAttempt.objects.count(), 4)
        self.assertEqual(JobOutbox.objects.count(), 2)
        self.assertEqual(UsageReservation.objects.count(), 2)
        self.assertEqual(MembershipAudit.objects.count(), 0)

    def test_pending_possible_effect_evidence_is_deduplicated_tenant_safe_and_read_only(self):
        job = self.seed()
        first = JobOutbox.objects.get(job=job)
        now = timezone.now()
        first_attempt = JobAttempt.objects.create(
            outbox=first, number=1, job_revision=0,
            status="started", expires_at=now - timedelta(seconds=30),
        )
        op = DispatchOperation.objects.create(
            workspace=self.workspace, job=job, outbox=first,
            attempt=first_attempt, source_code="synthetic",
            request_hash=job.request_hash, policy_version=1,
            policy_fingerprint="f" * 64, call_limit=1,
            status="unknown", unknown_at=now,
        )
        second_job = Job.objects.create(
            workspace=self.workspace, created_by=self.owner,
            status="queued", search={}, idempotency_key="second-safe-health",
            request_hash="e" * 64,
        )
        second_reservation = UsageReservation.objects.create(
            workspace=self.workspace, key="second-health-reservation",
            request_hash="e" * 64, leads=1, jobs=1, status="reserved",
        )
        second = JobOutbox.objects.create(
            job=second_job, reservation=second_reservation,
            submitted_by=self.owner, submitted_revision=0,
            source_snapshot=[], status="pending",
        )
        JobAttempt.objects.create(
            outbox=second, number=1, job_revision=0,
            status="done", expires_at=now - timedelta(seconds=10),
        )
        foreign_job = Job.objects.get(workspace=self.foreign_workspace)
        foreign_reservation = UsageReservation.objects.create(
            workspace=self.foreign_workspace, key="foreign-protected-reservation",
            request_hash="d" * 64, leads=1, jobs=1, status="reserved",
        )
        foreign_outbox = JobOutbox.objects.create(
            job=foreign_job, reservation=foreign_reservation,
            submitted_by=self.foreign, submitted_revision=0,
            source_snapshot=[], status="pending",
        )
        foreign_attempt = JobAttempt.objects.create(
            outbox=foreign_outbox, number=1, job_revision=0,
            status="started", expires_at=now - timedelta(seconds=20),
        )
        before = (
            JobAttempt.objects.count(), DispatchOperation.objects.count(),
            UsageReservation.objects.count(), JobOutbox.objects.count(),
        )
        api = f"/api/v1/workspaces/{self.workspace.id}/admin/health/"
        for actor in (self.owner, self.admin):
            self.client.force_login(actor)
            response = self.client.get(api)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["pending_possible_effect_intents"], 2)
            self.assertEqual(response.json()["outboxes"]["pending"], 2)
            self.assertEqual(response.json()["unknown_dispatch_operations"], 1)
            self.assertNotIn(str(op.provider_key), response.content.decode())
            self.assertNotIn(str(first_attempt.token), response.content.decode())
            self.assertNotIn(str(foreign_attempt.token), response.content.decode())
            self.assertNotIn("foreign-protected-reservation", response.content.decode())
            self.assertContains(
                self.client.get(self.path),
                "Pending intents with retained dispatch evidence",
            )
        self.assertEqual(
            before,
            (
                JobAttempt.objects.count(), DispatchOperation.objects.count(),
                UsageReservation.objects.count(), JobOutbox.objects.count(),
            ),
        )

    def test_no_invites_or_jobs_stays_explicit_zero(self):
        self.client.force_login(self.owner)
        report = self.client.get(self.path).context["report"]
        self.assertEqual(sum(report["jobs"].values()), 0)
        self.assertEqual(sum(report["outboxes"].values()), 0)
        self.assertEqual(sum(report["invitations"].values()), 0)
        self.assertEqual(report["expired_pending_outboxes"], 0)
        self.assertEqual(report["unknown_dispatch_operations"], 0)
        self.assertEqual(sum(report["pre_dispatch_attempts"].values()), 0)
        self.assertEqual(report["expired_leased_attempts"], 0)
        self.assertEqual(report["pending_possible_effect_intents"], 0)

    def test_viewer_foreign_revoked_and_anonymous_are_denied(self):
        self.seed()
        self.assertEqual(self.client.get(self.path).status_code, 302)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.foreign)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(
            self.client.get(f"/workspaces/{self.foreign_workspace.id}/admin/health/").status_code,
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
