"""Redacted, read-only internal billing diagnostics; never repairs state."""

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .models import BillingAccount, BillingEvent, Entitlement, User, Workspace
from .services import membership_for
from .usage_snapshot import usage_snapshot


@transaction.atomic
def billing_status(user, workspace_id):
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    if not User.objects.select_for_update().filter(pk=user.pk, is_active=True).exists():
        raise PermissionDenied("Current actor is unavailable.")
    member = membership_for(user, workspace_id, lock=True)
    if member.role not in {"owner", "admin"}:
        raise PermissionDenied("Billing diagnostics require a current administrator.")
    account = BillingAccount.objects.filter(workspace_id=workspace_id).first()
    entitlement = Entitlement.objects.filter(workspace_id=workspace_id).first()
    anomalies = []
    count = 0
    latest = None
    if account:
        events = BillingEvent.objects.filter(account=account)
        count = events.count()
        latest = events.order_by("-revision").first()
        if (account.revision, account.issued_at) != (
            (latest.revision, latest.issued_at) if latest else (0, None)
        ) or (latest and count != latest.revision):
            anomalies.append("ledger_order_mismatch")
        if events.exclude(workspace_id=workspace_id, issuer_code=account.issuer_code).exists():
            anomalies.append("binding_history_mismatch")
    if entitlement and entitlement.billing_account_id:
        if account is None or entitlement.billing_account_id != account.id:
            anomalies.append("entitlement_binding_mismatch")
        elif latest is None or (entitlement.active, entitlement.valid_until) != (
            latest.active,
            latest.valid_until,
        ):
            anomalies.append("entitlement_snapshot_mismatch")
    usage = usage_snapshot(user, workspace_id)
    return {
        "reconciliation_enabled": settings.SAAS_BILLING_RECONCILIATION_ENABLED is True,
        "binding_present": account is not None,
        "binding_enabled": bool(account and account.enabled),
        "binding_revision": account.revision if account else None,
        "event_count": count,
        "latest_revision": latest.revision if latest else None,
        "entitlement_present": entitlement is not None,
        "entitlement_current": bool(entitlement and entitlement.is_current),
        "entitlement_valid_until": entitlement.valid_until.isoformat()
        if entitlement and entitlement.valid_until
        else None,
        "anomalies": anomalies,
        "accounting": usage["accounting"],
        "counters": usage["counters"],
        "repair_performed": False,
    }
