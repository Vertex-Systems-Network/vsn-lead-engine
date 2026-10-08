import hashlib
import hmac
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .billing import reconcile_billing
from .models import BillingAccount, BillingEvent, Entitlement, Membership, UsageCounter, User
from .services import IdempotencyConflict, create_workspace
from .test_billing_evidence import KEY
from .usage import reserve_usage, settle_usage

SETTINGS = {
    "SAAS_BILLING_RECONCILIATION_ENABLED": True,
    "SAAS_BILLING_VERIFIERS": {"fixture": {"test": KEY}},
}


def fixture():
    user = User.objects.create_user(username="billing")
    workspace = create_workspace(user, {"name": "Billing", "timezone": "UTC"})
    account = BillingAccount.objects.create(
        workspace=workspace, issuer_code="fixture", enabled=True
    )
    return user, workspace, account


def signed(account, **changes):
    now = int(timezone.now().timestamp())
    data = {
        "version": 1,
        "key_id": "test",
        "event_ref": "fixture:billing:1",
        "issuer_code": account.issuer_code,
        "binding_id": str(account.id),
        "workspace_id": str(account.workspace_id),
        "revision": 1,
        "issued_at": now,
        "valid_until": now + 86400,
        "active": True,
        "limits": {"leads": 100, "jobs": 10, "provider_calls": 20, "exports": 5},
    }
    data.update(changes)
    body = json.dumps(data, sort_keys=True).encode()
    return body, hmac.new(KEY, body, hashlib.sha256).hexdigest()


@override_settings(**SETTINGS)
class BillingTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.account = fixture()
        self.proof = signed(self.account)

    def record(self, proof=None):
        return reconcile_billing(self.user, self.workspace.id, *(proof or self.proof))

    def test_default_service_and_binding_disabled_without_partial_writes(self):
        with override_settings(SAAS_BILLING_RECONCILIATION_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.record()
        BillingAccount.objects.filter(pk=self.account.id).update(enabled=False)
        with self.assertRaises(PermissionDenied):
            self.record()
        self.assertFalse(BillingEvent.objects.exists())
        self.assertFalse(Entitlement.objects.exists())
        self.assertFalse(BillingAccount._meta.get_field("enabled").default)

    def test_atomic_snapshot_and_exact_replay_retain_only_redacted_evidence(self):
        event, created = self.record()
        replay, repeated = self.record()
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(event.pk, replay.pk)
        entitlement = Entitlement.objects.get(workspace=self.workspace)
        self.assertTrue(entitlement.is_current)
        self.assertEqual((entitlement.lead_limit, entitlement.export_limit), (100, 5))
        self.assertEqual(entitlement.valid_until, event.valid_until)
        self.account.refresh_from_db()
        self.assertEqual(self.account.revision, 1)
        self.assertFalse(UsageCounter.objects.exists())
        self.assertNotIn("body", {f.name for f in BillingEvent._meta.fields})
        self.assertNotIn("signature", {f.name for f in BillingEvent._meta.fields})

    def test_conflicting_global_event_and_stale_or_gapped_revisions_are_denied(self):
        self.record()
        with self.assertRaises(IdempotencyConflict):
            self.record(
                signed(
                    self.account, limits={"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 1}
                )
            )
        for revision in (1, 3):
            with self.assertRaises(ValidationError):
                self.record(signed(self.account, event_ref="new", revision=revision))
        other = User.objects.create_user(username="foreign")
        workspace = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        account = BillingAccount.objects.create(
            workspace=workspace, issuer_code="fixture", enabled=True
        )
        with self.assertRaises(IdempotencyConflict):
            reconcile_billing(other, workspace.id, *signed(account))
        self.assertFalse(Entitlement.objects.filter(workspace=workspace).exists())
        self.assertEqual(BillingEvent.objects.count(), 1)

    def test_old_exact_replay_does_not_restore_revoked_snapshot(self):
        self.record()
        now = int(timezone.now().timestamp())
        self.record(
            signed(
                self.account,
                event_ref="revoked",
                revision=2,
                active=False,
                valid_until=now,
                limits=dict.fromkeys(("leads", "jobs", "provider_calls", "exports"), 0),
            )
        )
        self.assertFalse(self.record()[1])
        entitlement = Entitlement.objects.get(workspace=self.workspace)
        self.assertFalse(entitlement.is_current)
        self.assertEqual(entitlement.lead_limit, 0)
        self.account.refresh_from_db()
        self.assertEqual(self.account.revision, 2)

    def test_authority_signature_revocation_and_age_are_rechecked_on_replay(self):
        self.record()
        with override_settings(SAAS_BILLING_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.record()
        with patch(
            "core.billing_evidence.timezone.now", return_value=timezone.now() + timedelta(days=2)
        ):
            with self.assertRaises(ValidationError):
                self.record()
        for role in ("member", "viewer"):
            Membership.objects.filter(workspace=self.workspace).update(role=role)
            with self.assertRaises(PermissionDenied):
                self.record()
        Membership.objects.filter(workspace=self.workspace).update(role="owner")
        BillingAccount.objects.filter(pk=self.account.id).update(enabled=False)
        with self.assertRaises(PermissionDenied):
            self.record()
        self.assertFalse(Entitlement.objects.get(workspace=self.workspace).is_current)

    def test_foreign_payload_and_binding_reassignment_fail_closed(self):
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(ValidationError):
            self.record(signed(self.account, workspace_id=str(other.id)))
        self.record()
        BillingAccount.objects.filter(pk=self.account.id).update(workspace=other)
        with self.assertRaises(PermissionDenied):
            reconcile_billing(
                self.user, other.id, *signed(BillingAccount.objects.get(pk=self.account.id))
            )
        self.assertFalse(Entitlement.objects.get(workspace=self.workspace).is_current)

    def test_regressing_issuance_and_failed_persistence_roll_back_all_state(self):
        self.record()
        old = int(timezone.now().timestamp()) - 100
        with self.assertRaises(ValidationError):
            self.record(signed(self.account, event_ref="older", revision=2, issued_at=old))
        with patch(
            "core.billing.Entitlement.objects.update_or_create",
            side_effect=RuntimeError("injected"),
        ):
            with self.assertRaises(RuntimeError):
                self.record(signed(self.account, event_ref="next", revision=2))
        self.account.refresh_from_db()
        self.assertEqual(self.account.revision, 1)
        self.assertEqual(BillingEvent.objects.count(), 1)
        self.assertEqual(Entitlement.objects.get(workspace=self.workspace).lead_limit, 100)

    def test_downgrade_preserves_reservations_counters_and_allows_past_settlement(self):
        self.record()
        reservation = reserve_usage(self.user, self.workspace.id, "pending", {"leads": 90})
        self.record(
            signed(
                self.account,
                event_ref="downgrade",
                revision=2,
                limits={"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 1},
            )
        )
        with self.assertRaises(ValidationError):
            reserve_usage(self.user, self.workspace.id, "new", {"leads": 1})
        reservation.refresh_from_db()
        self.assertEqual((reservation.status, reservation.leads), ("reserved", 90))
        Entitlement.objects.filter(workspace=self.workspace).update(valid_until=timezone.now())
        settle_usage(self.user, self.workspace.id, reservation.id, {"leads": 80})
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 80)

    def test_migration_refuses_loss_of_billing_or_deadline_evidence(self):
        module = importlib.import_module("core.migrations.0017_billing_reconciliation")
        with self.assertRaises(RuntimeError):
            module.protect_billing_rollback(apps, SimpleNamespace(connection=connection))


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
@override_settings(**SETTINGS)
class BillingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user, self.workspace, self.account = fixture()

    def race(self, callbacks):
        barrier = Barrier(2)

        def run(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    callback()
                    return "ok"
                except (IdempotencyConflict, ValidationError, PermissionDenied):
                    return "denied"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, callbacks))

    def test_duplicate_event_commits_once(self):
        proof = signed(self.account)

        def callback():
            return reconcile_billing(self.user, self.workspace.id, *proof)

        self.assertEqual(self.race([callback, callback]), ["ok", "ok"])
        self.assertEqual(BillingEvent.objects.count(), 1)
        self.assertEqual(BillingAccount.objects.get().revision, 1)

    def test_conflicting_revision_has_one_winner(self):
        callbacks = [
            lambda p=p: reconcile_billing(self.user, self.workspace.id, *p)
            for p in [signed(self.account), signed(self.account, event_ref="other")]
        ]
        self.assertCountEqual(self.race(callbacks), ["ok", "denied"])
        self.assertEqual(BillingEvent.objects.count(), 1)

    def test_revocation_and_reservation_serialize_without_refunds(self):
        reconcile_billing(self.user, self.workspace.id, *signed(self.account))
        now = int(timezone.now().timestamp())
        proof = signed(
            self.account,
            event_ref="revoked",
            revision=2,
            active=False,
            valid_until=now,
            limits=dict.fromkeys(("leads", "jobs", "provider_calls", "exports"), 0),
        )
        results = self.race(
            [
                lambda: reconcile_billing(self.user, self.workspace.id, *proof),
                lambda: reserve_usage(self.user, self.workspace.id, "racing", {"leads": 10}),
            ]
        )
        self.assertIn("ok", results)
        self.assertFalse(Entitlement.objects.get(workspace=self.workspace).is_current)
        self.assertEqual(
            UsageCounter.objects.filter(workspace=self.workspace, leads__gt=0).count(), 0
        )
        with self.assertRaises(PermissionDenied):
            reserve_usage(self.user, self.workspace.id, "later", {"leads": 1})

    def test_same_issuer_event_across_tenants_commits_once(self):
        other = User.objects.create_user(username="other-billing")
        workspace = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        account = BillingAccount.objects.create(
            workspace=workspace, issuer_code="fixture", enabled=True
        )
        callbacks = [
            lambda: reconcile_billing(self.user, self.workspace.id, *signed(self.account)),
            lambda: reconcile_billing(other, workspace.id, *signed(account)),
        ]
        self.assertCountEqual(self.race(callbacks), ["ok", "denied"])
        self.assertEqual(BillingEvent.objects.count(), 1)
        self.assertEqual(Entitlement.objects.count(), 1)

    def test_revocation_and_dispatch_start_serialize_and_retain_reserved_capacity(self):
        from .attempts import claim_pre_dispatch
        from .dispatch import begin_dispatch
        from .jobs import enqueue_job
        from .models import JobOutbox
        from .services import create_draft
        from .test_jobs import fixture as job_fixture

        # Reuse the synthetic source-policy fixture, with a separate bound workspace.
        self.user, self.workspace, draft = job_fixture()
        self.account = BillingAccount.objects.create(
            workspace=self.workspace, issuer_code="fixture", enabled=True
        )
        reconcile_billing(self.user, self.workspace.id, *signed(self.account))
        # fixture() already saved a normalized draft; no provider runs.
        draft, _ = create_draft(self.user, self.workspace.id, draft.search, "dispatch-billing")
        enqueue_job(self.user, self.workspace.id, draft.id, 0)
        outbox = JobOutbox.objects.get(job=draft)
        lease = claim_pre_dispatch(outbox.id)
        now = int(timezone.now().timestamp())
        proof = signed(
            self.account,
            event_ref="revoked",
            revision=2,
            active=False,
            valid_until=now,
            limits=dict.fromkeys(("leads", "jobs", "provider_calls", "exports"), 0),
        )
        self.race(
            [
                lambda: reconcile_billing(self.user, self.workspace.id, *proof),
                lambda: begin_dispatch(outbox.id, lease.token),
            ]
        )
        outbox.reservation.refresh_from_db()
        self.assertEqual(outbox.reservation.status, "reserved")
        self.assertFalse(Entitlement.objects.get(workspace=self.workspace).is_current)
