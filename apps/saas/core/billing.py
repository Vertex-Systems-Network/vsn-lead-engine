"""Disabled internal reconciliation. No webhook, payment, period reset or provider."""

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from .billing_evidence import BillingBinding, verified_billing_event
from .models import BillingAccount, BillingEvent, Entitlement, User, Workspace
from .services import IdempotencyConflict, membership_for
from .usage import COUNTERS


@transaction.atomic
def reconcile_billing(user, workspace_id, body, signature):
    if settings.SAAS_BILLING_RECONCILIATION_ENABLED is not True:
        raise PermissionDenied("Billing reconciliation is unavailable.")
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    if not User.objects.select_for_update().filter(pk=user.pk, is_active=True).exists():
        raise PermissionDenied("Current actor is unavailable.")
    membership = membership_for(user, workspace_id, lock=True)
    if membership.role not in {"owner", "admin"}:
        raise PermissionDenied("Billing reconciliation requires a current administrator.")
    account = BillingAccount.objects.select_for_update().filter(workspace_id=workspace_id).first()
    if account is None or not account.enabled:
        raise PermissionDenied("Billing reconciliation is unavailable.")
    if (
        BillingEvent.objects.filter(account=account)
        .exclude(workspace_id=workspace_id, issuer_code=account.issuer_code)
        .exists()
    ):
        raise PermissionDenied("Billing binding requires reconciliation.")
    latest = BillingEvent.objects.filter(account=account).order_by("-revision").first()
    if (account.revision, account.issued_at) != (
        (latest.revision, latest.issued_at) if latest else (0, None)
    ):
        raise PermissionDenied("Billing binding requires reconciliation.")
    event = verified_billing_event(
        body, signature, BillingBinding(account.id, account.workspace_id, account.issuer_code)
    )
    previous = BillingEvent.objects.filter(
        issuer_code=account.issuer_code, event_ref=event.event_ref
    ).first()
    if previous:
        if previous.account_id != account.id or previous.body_hash != event.body_hash:
            raise IdempotencyConflict()
        # Recheck authority/signature/freshness, never reapply an older snapshot.
        return previous, False
    if event.revision != account.revision + 1 or (
        account.issued_at is not None and event.issued_at < account.issued_at
    ):
        raise ValidationError("Billing event ordering requires reconciliation.")
    try:
        # Global issuer/event uniqueness also arbitrates different workspace locks.
        with transaction.atomic():
            recorded = BillingEvent.objects.create(
                account=account,
                workspace_id=workspace_id,
                issuer_code=account.issuer_code,
                event_ref=event.event_ref,
                revision=event.revision,
                body_hash=event.body_hash,
                key_id=event.key_id,
                issued_at=event.issued_at,
                valid_until=event.valid_until,
                active=event.active,
                actor=user,
            )
            Entitlement.objects.update_or_create(
                workspace_id=workspace_id,
                defaults={
                    "active": event.active,
                    "valid_until": event.valid_until,
                    "billing_account": account,
                    **{limit: getattr(event, name) for name, limit in COUNTERS.items()},
                },
            )
            account.revision = event.revision
            account.issued_at = event.issued_at
            account.save(update_fields=["revision", "issued_at"])
    except IntegrityError:
        raise IdempotencyConflict() from None
    return recorded, True
