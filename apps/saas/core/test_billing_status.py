import io
import json
from datetime import timedelta
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .billing import reconcile_billing
from .billing_status import billing_status
from .models import (
    BillingAccount,
    BillingEvent,
    Entitlement,
    Membership,
    UsageCounter,
    UsageReservation,
    User,
)
from .test_billing import SETTINGS, fixture, signed


class BillingStatusTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.account = fixture()

    def status(self):
        return billing_status(self.user, self.workspace.id)

    def test_missing_internal_grants_are_not_provisioned(self):
        self.account.delete()
        status = self.status()
        self.assertFalse(status["binding_present"])
        self.assertFalse(status["entitlement_current"])
        self.assertFalse(status["repair_performed"])
        self.assertEqual(status["anomalies"], [])
        self.assertFalse(Entitlement.objects.exists())
        self.assertFalse(UsageCounter.objects.exists())
        self.assertFalse(UsageReservation.objects.exists())

    @override_settings(**SETTINGS)
    def test_redacted_expired_snapshot_and_usage_are_observed_without_repair(self):
        reconcile_billing(self.user, self.workspace.id, *signed(self.account))
        deadline = timezone.now() + timedelta(days=2)
        with override_settings(SAAS_BILLING_RECONCILIATION_ENABLED=False):
            status = self.status()
            self.assertFalse(status["reconciliation_enabled"])
            self.assertTrue(status["entitlement_current"])
        with self.settings():
            from unittest.mock import patch

            with patch("core.models.timezone.now", return_value=deadline):
                status = self.status()
                self.assertFalse(status["entitlement_current"])
        self.assertEqual(status["event_count"], 1)
        self.assertEqual(status["anomalies"], [])
        for hidden in [
            "fixture:billing:1",
            "fixture",
            "key_id",
            str(self.user.id),
            str(self.workspace.id),
            str(self.account.id),
            BillingEvent.objects.get().body_hash,
        ]:
            self.assertNotIn(hidden, json.dumps(status))
        self.assertTrue(Entitlement.objects.get(workspace=self.workspace).active)
        self.assertFalse(UsageCounter.objects.exists())

    @override_settings(**SETTINGS)
    def test_ledger_and_snapshot_mismatches_are_reported_without_rewriting_evidence(self):
        reconcile_billing(self.user, self.workspace.id, *signed(self.account))
        BillingAccount.objects.filter(pk=self.account.id).update(revision=5, issuer_code="changed")
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        status = self.status()
        self.assertEqual(
            set(status["anomalies"]),
            {"ledger_order_mismatch", "binding_history_mismatch", "entitlement_snapshot_mismatch"},
        )
        self.assertEqual(BillingAccount.objects.get().revision, 5)
        self.assertFalse(Entitlement.objects.get().active)
        self.assertEqual(BillingEvent.objects.count(), 1)

    def test_current_admin_tenant_and_revoked_membership_boundaries(self):
        for role in ["member", "viewer"]:
            Membership.objects.filter(workspace=self.workspace).update(role=role)
            with self.assertRaises(PermissionDenied):
                self.status()
        with self.assertRaises(Http404):
            billing_status(self.user, uuid4())
        Membership.objects.filter(workspace=self.workspace).delete()
        with self.assertRaises(Http404):
            self.status()

    def test_command_reports_only_summary_and_generic_context_failure(self):
        output = io.StringIO()
        call_command(
            "billing_status",
            actor=str(self.user.id),
            workspace=str(self.workspace.id),
            stdout=output,
        )
        self.assertFalse(json.loads(output.getvalue())["repair_performed"])
        for actor, workspace in [
            ("bad", str(self.workspace.id)),
            (str(uuid4()), str(self.workspace.id)),
            (str(self.user.id), str(uuid4())),
        ]:
            with self.assertRaisesMessage(CommandError, "Billing diagnostics are unavailable"):
                call_command("billing_status", actor=actor, workspace=workspace)

    @override_settings(**SETTINGS)
    def test_disabled_actor_cannot_diagnose_or_reconcile_with_stale_user_object(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.status()
        with self.assertRaises(PermissionDenied):
            reconcile_billing(self.user, self.workspace.id, *signed(self.account))
        self.assertFalse(BillingEvent.objects.exists())
