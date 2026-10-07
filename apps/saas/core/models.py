import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True)


class Membership(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=8, choices=[(r, r) for r in ("owner", "admin", "member", "viewer")]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="saas_unique_membership"),
            models.CheckConstraint(
                condition=models.Q(role__in=["owner", "admin", "member", "viewer"]),
                name="saas_valid_role",
            ),
        ]


class Job(models.Model):
    """Saved search intent. Internal enqueue persists an outbox; no provider dispatch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    search = models.JSONField()
    status = models.CharField(max_length=16, default="draft", editable=False)
    revision = models.PositiveIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"], name="saas_job_idempotency"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "draft",
                        "queued",
                        "running",
                        "partial",
                        "completed",
                        "failed",
                        "paused",
                        "cancelled",
                    ]
                ),
                name="saas_valid_job_status",
            ),
            models.CheckConstraint(
                condition=models.Q(revision__gte=0), name="saas_job_revision_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "-created_at"], name="saas_job_workspace_created")
        ]


class MembershipAudit(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="membership_actions"
    )
    target_user_id = models.UUIDField()
    action = models.CharField(max_length=16)
    previous_role = models.CharField(max_length=8)
    new_role = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginBucket(models.Model):
    """Short-lived keyed fingerprints only; no raw username or IP."""

    fingerprint = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)


class Entitlement(models.Model):
    """Internal, fail-closed capabilities; no billing provider is activated."""

    workspace = models.OneToOneField(Workspace, primary_key=True, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    lead_limit = models.PositiveIntegerField(default=0)
    job_limit = models.PositiveIntegerField(default=0)
    provider_call_limit = models.PositiveIntegerField(default=0)
    export_limit = models.PositiveIntegerField(default=0)


class UsageCounter(models.Model):
    workspace = models.OneToOneField(Workspace, primary_key=True, on_delete=models.CASCADE)
    leads = models.PositiveIntegerField(default=0)
    jobs = models.PositiveIntegerField(default=0)
    provider_calls = models.PositiveIntegerField(default=0)
    exports = models.PositiveIntegerField(default=0)


class UsageReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    leads = models.PositiveIntegerField(default=0)
    jobs = models.PositiveIntegerField(default=0)
    provider_calls = models.PositiveIntegerField(default=0)
    exports = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=8, default="reserved")
    settlement = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="saas_reservation_key"),
            models.CheckConstraint(
                condition=models.Q(status__in=["reserved", "settled", "released"]),
                name="saas_reservation_status",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "status"], name="saas_reservation_workspace")]


class SourcePolicy(models.Model):
    """Trusted internal catalog only. Empty/unknown rights and costs fail closed."""

    code = models.CharField(max_length=64, primary_key=True)
    version = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=False)
    free_collection = models.BooleanField(default=False)
    countries = models.JSONField(default=list)
    categories = models.JSONField(default=list)
    statuses = models.JSONField(default=list)
    fields = models.JSONField(default=list)
    evidence = models.JSONField(default=dict)
    controls = models.JSONField(default=dict)
    max_provider_calls = models.PositiveIntegerField(default=0)


class JobOutbox(models.Model):
    """Durable pre-dispatch intent. No consumer or external call is enabled."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(Job, on_delete=models.CASCADE)
    reservation = models.OneToOneField(UsageReservation, on_delete=models.PROTECT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submitted_revision = models.PositiveIntegerField()
    source_snapshot = models.JSONField()
    status = models.CharField(max_length=9, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "cancelled"]),
                name="saas_outbox_status",
            )
        ]
