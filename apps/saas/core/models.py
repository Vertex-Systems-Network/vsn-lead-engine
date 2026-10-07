import uuid
from django.contrib.auth.models import AbstractUser
from django.conf import settings
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
    role = models.CharField(max_length=8, choices=[(r, r) for r in ("owner", "admin", "member", "viewer")])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="saas_unique_membership"),
            models.CheckConstraint(condition=models.Q(role__in=["owner", "admin", "member", "viewer"]), name="saas_valid_role"),
        ]


class Job(models.Model):
    """Saved draft intent only. This slice cannot enqueue or dispatch a provider."""
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
            models.UniqueConstraint(fields=["workspace", "idempotency_key"], name="saas_job_idempotency"),
            models.CheckConstraint(condition=models.Q(status__in=["draft", "queued", "running", "partial", "completed", "failed", "paused", "cancelled"]), name="saas_valid_job_status"),
            models.CheckConstraint(condition=models.Q(revision__gte=0), name="saas_job_revision_nonnegative"),
        ]
        indexes = [models.Index(fields=["workspace", "-created_at"], name="saas_job_workspace_created")]


class MembershipAudit(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="membership_actions")
    target_user_id = models.UUIDField()
    action = models.CharField(max_length=16)
    previous_role = models.CharField(max_length=8)
    new_role = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
