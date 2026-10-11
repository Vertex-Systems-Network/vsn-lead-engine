"""Trusted bounded cleanup of exclusively pre-dispatch intents; no background loop."""

from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .jobs import has_possible_effect_evidence
from .models import DispatchOperation, Job, JobAttempt, JobOutbox, UsageReservation, Workspace


@transaction.atomic
def expire_one(intent_id):
    intent = JobOutbox.objects.select_related("job").filter(pk=intent_id).first()
    if intent is None:
        return False
    Workspace.objects.select_for_update().get(pk=intent.job.workspace_id)
    job = Job.objects.select_for_update().get(pk=intent.job_id)
    intent = JobOutbox.objects.select_for_update().get(pk=intent_id)
    reservation = UsageReservation.objects.select_for_update().get(pk=intent.reservation_id)
    # Never infer that a running, settled, legacy or unknown-outcome job is safe to refund.
    if (
        intent.status != "pending"
        or job.status != "queued"
        or intent.expires_at is None
        or intent.expires_at > timezone.now()
        or reservation.status != "reserved"
        or reservation.workspace_id != job.workspace_id
        or job.revision >= 2147483647
        or has_possible_effect_evidence(intent)
    ):
        return False
    reservation.status = "released"
    reservation.save(update_fields=["status", "updated_at"])
    JobAttempt.objects.filter(outbox=intent, status="leased").update(status="cancelled")
    intent.status = "cancelled"
    intent.save(update_fields=["status", "updated_at"])
    job.status = "cancelled"
    job.revision += 1
    job.save(update_fields=["status", "revision", "updated_at"])
    return True


def eligible_expired_pending_outboxes(*, at):
    """Read-only candidate query; no guarantee a row will still qualify later.

    Shared by the bounded operator cleanup and owner/admin health snapshot.
    Never include an intent with durable possible-effect evidence, a foreign
    reservation or a revision that cannot be advanced safely.
    """
    return JobOutbox.objects.filter(
        status="pending",
        job__status="queued",
        job__revision__lt=2147483647,
        reservation__status="reserved",
        reservation__workspace_id=F("job__workspace_id"),
        expires_at__lte=at,
    ).filter(
        ~Exists(DispatchOperation.objects.filter(outbox_id=OuterRef("pk"))),
        ~Exists(
            JobAttempt.objects.filter(outbox_id=OuterRef("pk"), status__in=("started", "done"))
        ),
    )


def expire_pending_intents(*, limit=100):
    """Expire up to `limit` safe candidates, not blocked possible-effect rows."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("Cleanup batch must contain 1–100 intents.")
    # Candidate selection is advisory; expire_one() rechecks under the
    # workspace lock, so races cannot make an unsafe refund permissible.
    ids = list(
        eligible_expired_pending_outboxes(at=timezone.now())
        .order_by("expires_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    return {"examined": len(ids), "expired": sum(expire_one(intent_id) for intent_id in ids)}
