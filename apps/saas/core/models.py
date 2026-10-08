import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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


class DailySchedule(models.Model):
    """Immutable daily draft configuration. No scheduler/activation endpoint exists."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.CharField(max_length=128)
    timezone = models.CharField(max_length=64)
    local_time = models.TimeField()
    search = models.JSONField()
    request_hash = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="saas_schedule_key"),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="saas_schedule_revision"
            ),
        ]


class ScheduleOccurrence(models.Model):
    """One local-day decision with a linked draft, never an execution claim."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schedule = models.ForeignKey(DailySchedule, on_delete=models.PROTECT)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    schedule_revision = models.PositiveIntegerField()
    local_date = models.DateField()
    local_time = models.TimeField()
    timezone = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    scheduled_for = models.DateTimeField(null=True)
    utc_offset_seconds = models.IntegerField(null=True)
    resolution = models.CharField(max_length=20)
    job = models.OneToOneField(Job, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Revisions cannot create a second draft for the same local day.
            models.UniqueConstraint(
                fields=["schedule", "local_date"], name="saas_daily_occurrence"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        resolution="skipped_day",
                        scheduled_for__isnull=True,
                        utc_offset_seconds__isnull=True,
                        job__isnull=True,
                    )
                    | models.Q(
                        resolution__in=["normal", "gap_forward", "ambiguous_earlier"],
                        scheduled_for__isnull=False,
                        utc_offset_seconds__isnull=False,
                        job__isnull=False,
                    )
                ),
                name="saas_occurrence_decision",
            ),
        ]


class LoginBucket(models.Model):
    """Short-lived keyed fingerprints only; no raw username or IP."""

    fingerprint = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)


class BillingAccount(models.Model):
    """Trusted local binding; disabled by default, no customer/payment identifiers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.PROTECT)
    issuer_code = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=0)
    issued_at = models.DateTimeField(null=True)


class BillingEvent(models.Model):
    """Redacted reconciliation ledger. No signed payload, signature or payment data."""

    account = models.ForeignKey(BillingAccount, on_delete=models.PROTECT)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    issuer_code = models.CharField(max_length=64)
    event_ref = models.CharField(max_length=96)
    revision = models.PositiveIntegerField()
    body_hash = models.CharField(max_length=64)
    key_id = models.CharField(max_length=64)
    issued_at = models.DateTimeField()
    valid_until = models.DateTimeField()
    active = models.BooleanField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["issuer_code", "event_ref"], name="saas_billing_event"),
            models.UniqueConstraint(fields=["account", "revision"], name="saas_billing_revision"),
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="saas_billing_positive"
            ),
        ]


class Entitlement(models.Model):
    """Internal, fail-closed capabilities; no billing provider is activated."""

    workspace = models.OneToOneField(Workspace, primary_key=True, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    valid_until = models.DateTimeField(null=True)
    billing_account = models.ForeignKey(BillingAccount, null=True, on_delete=models.PROTECT)
    lead_limit = models.PositiveIntegerField(default=0)
    job_limit = models.PositiveIntegerField(default=0)
    provider_call_limit = models.PositiveIntegerField(default=0)
    export_limit = models.PositiveIntegerField(default=0)

    @property
    def is_current(self):
        if not self.active or (self.valid_until is not None and self.valid_until <= timezone.now()):
            return False
        if self.billing_account_id is not None:
            return (
                self.valid_until is not None
                and BillingAccount.objects.filter(
                    pk=self.billing_account_id, workspace_id=self.workspace_id, enabled=True
                ).exists()
            )
        # Existing explicitly provisioned internal development grants remain compatible.
        return True


class UsagePeriod(models.Model):
    """Explicit internal window only; no payment, automatic reset or activation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    key = models.CharField(max_length=128)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=6, default="open")
    settled_snapshot = models.JSONField(null=True)
    closed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="saas_period_key"),
            models.UniqueConstraint(
                fields=["workspace"], condition=models.Q(status="open"), name="saas_one_open_period"
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")), name="saas_period_order"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="open", closed_at__isnull=True, settled_snapshot__isnull=True)
                    | models.Q(
                        status="closed", closed_at__isnull=False, settled_snapshot__isnull=False
                    )
                ),
                name="saas_period_close_evidence",
            ),
        ]


class UsageCounter(models.Model):
    period = models.OneToOneField(UsagePeriod, null=True, on_delete=models.PROTECT)
    workspace = models.OneToOneField(Workspace, primary_key=True, on_delete=models.CASCADE)
    leads = models.PositiveIntegerField(default=0)
    jobs = models.PositiveIntegerField(default=0)
    provider_calls = models.PositiveIntegerField(default=0)
    exports = models.PositiveIntegerField(default=0)


class UsageReservation(models.Model):
    period = models.ForeignKey(UsagePeriod, null=True, on_delete=models.PROTECT)
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
    expires_at = models.DateTimeField(null=True, db_index=True)
    source_snapshot = models.JSONField()
    result_protocol = models.PositiveSmallIntegerField(default=2, editable=False)
    status = models.CharField(max_length=9, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "cancelled", "started", "done"]),
                name="saas_outbox_status",
            ),
            models.CheckConstraint(
                condition=models.Q(result_protocol__in=[2, 3]), name="saas_outbox_protocol"
            ),
        ]


class JobAttempt(models.Model):
    """Pre-dispatch lease only; external execution is deliberately unavailable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outbox = models.ForeignKey(JobOutbox, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveIntegerField()
    job_revision = models.PositiveIntegerField()
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=9, default="leased")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["outbox", "number"], name="saas_attempt_number"),
            models.UniqueConstraint(
                fields=["outbox"],
                condition=models.Q(status="leased"),
                name="saas_one_active_attempt",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["leased", "expired", "cancelled", "started", "done"]
                ),
                name="saas_attempt_status",
            ),
        ]


class DispatchOperation(models.Model):
    """Write-ahead uncertainty ledger; no external caller is enabled."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    job = models.ForeignKey(Job, on_delete=models.PROTECT)
    outbox = models.ForeignKey(JobOutbox, on_delete=models.PROTECT, related_name="operations")
    attempt = models.ForeignKey(JobAttempt, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    provider_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    request_hash = models.CharField(max_length=64)
    policy_version = models.PositiveIntegerField()
    policy_fingerprint = models.CharField(max_length=64)
    call_limit = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=8, default="started")
    created_at = models.DateTimeField(auto_now_add=True)
    unknown_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["outbox", "source_code"], name="saas_dispatch_source"),
            models.CheckConstraint(
                condition=models.Q(status__in=["started", "unknown", "success", "noeffect"]),
                name="saas_dispatch_status",
            ),
            models.CheckConstraint(
                condition=models.Q(policy_version__gte=1), name="saas_dispatch_policy_version"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="started", unknown_at__isnull=True)
                    | models.Q(status="unknown", unknown_at__isnull=False)
                    | models.Q(status__in=["success", "noeffect"])
                ),
                name="saas_dispatch_unknown_time",
            ),
        ]


class DispatchReceipt(models.Model):
    """Redacted terminal proof metadata. Raw body, signatures and secrets are omitted."""

    operation = models.OneToOneField(DispatchOperation, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    receipt_ref = models.CharField(max_length=96)
    key_id = models.CharField(max_length=64)
    body_hash = models.CharField(max_length=64)
    outcome = models.CharField(max_length=8)
    provider_calls = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source_code", "receipt_ref"], name="saas_receipt_ref"),
            models.CheckConstraint(
                condition=models.Q(outcome__in=["success", "noeffect"]), name="saas_receipt_outcome"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(outcome="noeffect", provider_calls=0)
                    | models.Q(outcome="success", provider_calls__gte=1)
                ),
                name="saas_receipt_effect_calls",
            ),
        ]


class CandidateEvidence(models.Model):
    """Redacted internal event ledger; never accepted leads or retained payloads."""

    operation = models.OneToOneField(DispatchOperation, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    event_ref = models.CharField(max_length=96)
    body_hash = models.CharField(max_length=64)
    candidate_count = models.PositiveIntegerField()
    earliest_delete_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_code", "event_ref"], name="saas_candidate_event"
            ),
            models.CheckConstraint(
                condition=models.Q(candidate_count__gte=1, candidate_count__lte=25),
                name="saas_candidate_count",
            ),
        ]


class ResultAcceptance(models.Model):
    """Version-2 terminal evidence, isolated from zero-lead DispatchReceipt v1."""

    operation = models.OneToOneField(DispatchOperation, on_delete=models.PROTECT)
    candidate = models.OneToOneField(CandidateEvidence, on_delete=models.PROTECT)
    receipt_ref = models.CharField(max_length=96)
    source_code = models.CharField(max_length=64)
    source_key_id = models.CharField(max_length=64)
    dedupe_key_id = models.CharField(max_length=64)
    body_hash = models.CharField(max_length=64)
    namespace = models.CharField(max_length=96)
    accepted_count = models.PositiveIntegerField()
    provider_calls = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_code", "receipt_ref"], name="saas_acceptance_ref"
            ),
            models.CheckConstraint(
                condition=models.Q(accepted_count__gte=1, accepted_count__lte=25),
                name="saas_accepted_count",
            ),
            models.CheckConstraint(
                condition=models.Q(provider_calls__gte=1), name="saas_acceptance_calls"
            ),
        ]


class ResultBatch(models.Model):
    """V3 server-owned identity scaffold; no intake or accounting service is exposed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.ForeignKey(
        DispatchOperation, on_delete=models.PROTECT, related_name="batches"
    )
    ordinal = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["operation", "ordinal"], name="saas_batch_ordinal"),
            models.CheckConstraint(condition=models.Q(ordinal__gte=1), name="saas_batch_positive"),
        ]


class BatchCandidateEvidence(models.Model):
    """Redacted v3 candidate metadata; distinct from the v2 one-operation event."""

    batch = models.OneToOneField(ResultBatch, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    event_ref = models.CharField(max_length=96)
    body_hash = models.CharField(max_length=64)
    candidate_count = models.PositiveIntegerField()
    earliest_delete_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_code", "event_ref"], name="saas_batch_candidate_ref"
            ),
            models.CheckConstraint(
                condition=models.Q(candidate_count__gte=1, candidate_count__lte=25),
                name="saas_batch_candidate_count",
            ),
        ]


class BatchAcceptance(models.Model):
    """V3 evidence metadata only; creating a row never accepts payload or settles usage."""

    candidate = models.OneToOneField(BatchCandidateEvidence, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    receipt_ref = models.CharField(max_length=96)
    source_key_id = models.CharField(max_length=64)
    dedupe_key_id = models.CharField(max_length=64)
    body_hash = models.CharField(max_length=64)
    namespace = models.CharField(max_length=96)
    accepted_count = models.PositiveIntegerField()
    provider_calls = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_code", "receipt_ref"], name="saas_batch_accept_ref"
            ),
            models.CheckConstraint(
                condition=models.Q(accepted_count__gte=1, accepted_count__lte=25),
                name="saas_batch_accepted_count",
            ),
            models.CheckConstraint(
                condition=models.Q(provider_calls__gte=1), name="saas_batch_calls"
            ),
        ]


class SourceBatchTerminal(models.Model):
    """Redacted final-manifest coordinates; no completeness or settlement inferred."""

    operation = models.OneToOneField(DispatchOperation, on_delete=models.PROTECT)
    source_code = models.CharField(max_length=64)
    receipt_ref = models.CharField(max_length=96)
    source_key_id = models.CharField(max_length=64)
    body_hash = models.CharField(max_length=64)
    batch_set_hash = models.CharField(max_length=64)
    batch_count = models.PositiveIntegerField()
    accepted_count = models.PositiveIntegerField()
    provider_calls = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_code", "receipt_ref"], name="saas_batch_terminal_ref"
            ),
            models.CheckConstraint(
                condition=models.Q(batch_count=0, accepted_count=0)
                | models.Q(
                    batch_count__gte=1,
                    accepted_count__gte=models.F("batch_count"),
                    accepted_count__lte=25 * models.F("batch_count"),
                    provider_calls__gte=1,
                ),
                name="saas_batch_terminal_counts",
            ),
        ]


class AcceptedResult(models.Model):
    """Isolated tenant payload with source-derived eligibility/deletion deadline."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    job = models.ForeignKey(Job, on_delete=models.PROTECT)
    acceptance = models.ForeignKey(ResultAcceptance, null=True, on_delete=models.PROTECT)
    batch_acceptance = models.ForeignKey(BatchAcceptance, null=True, on_delete=models.PROTECT)
    batch_position = models.PositiveSmallIntegerField(null=True)
    record_ref = models.CharField(max_length=96, null=True)
    country = models.CharField(max_length=2)
    category = models.CharField(max_length=120)
    fields = models.JSONField()
    field_lineage = models.JSONField()
    observed_at = models.DateTimeField()
    delete_at = models.DateTimeField()
    purpose = models.CharField(max_length=64)
    retention_version = models.CharField(max_length=64)
    erased_at = models.DateTimeField(null=True, editable=False)
    erased_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["acceptance", "record_ref"], name="saas_accepted_record"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    acceptance__isnull=False,
                    batch_acceptance__isnull=True,
                    batch_position__isnull=True,
                )
                | models.Q(
                    acceptance__isnull=True,
                    batch_acceptance__isnull=False,
                    batch_position__isnull=False,
                    batch_position__gte=1,
                    batch_position__lte=25,
                ),
                name="saas_result_protocol_link",
            ),
            models.UniqueConstraint(
                fields=["batch_acceptance", "record_ref"], name="saas_batch_result_ref"
            ),
            models.UniqueConstraint(
                fields=["batch_acceptance", "batch_position"], name="saas_batch_result_position"
            ),
            models.CheckConstraint(
                condition=models.Q(country__in=["US", "CA"]), name="saas_accepted_country"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        erased_at__isnull=True, erased_by__isnull=True, record_ref__isnull=False
                    )
                    & ~models.Q(record_ref="")
                )
                | models.Q(
                    erased_at__isnull=False,
                    erased_by__isnull=False,
                    record_ref__isnull=True,
                    fields={},
                    field_lineage={},
                    category="",
                    purpose="",
                    retention_version="",
                ),
                name="saas_result_erasure_state",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "job", "id"], name="saas_result_job"),
            models.Index(
                fields=["workspace", "delete_at", "id"],
                condition=models.Q(erased_at__isnull=True),
                name="saas_result_expiry",
            ),
        ]


class AcceptedFingerprint(models.Model):
    """Tenant dedupe backstop; signed isolated R2 evidence remains mandatory."""

    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    result = models.ForeignKey(AcceptedResult, on_delete=models.PROTECT)
    token = models.CharField(max_length=26)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "token"], name="saas_accepted_token")
        ]


class ResultExport(models.Model):
    """Redacted once-only export accounting; CSV payloads are never persisted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    job = models.ForeignKey(Job, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reservation = models.OneToOneField(UsageReservation, on_delete=models.PROTECT)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    content_digest = models.CharField(max_length=64)
    record_count = models.PositiveIntegerField()
    delete_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["workspace", "job", "-created_at", "-id"], name="saas_export_job_history"
            ),
            models.Index(
                fields=["workspace", "job", "created_by", "-created_at", "-id"],
                name="saas_export_actor_history",
            ),
        ]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="saas_export_key"),
            models.CheckConstraint(
                condition=models.Q(record_count__gte=1, record_count__lte=25),
                name="saas_export_count",
            ),
        ]
