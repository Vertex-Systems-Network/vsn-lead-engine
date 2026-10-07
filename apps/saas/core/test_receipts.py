import hashlib
import hmac
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .attempts import claim_pre_dispatch
from .dispatch import begin_dispatch, mark_outcome_unknown
from .jobs import enqueue_job
from .models import (
    DispatchReceipt,
    Entitlement,
    JobAttempt,
    JobOutbox,
    Membership,
    SourcePolicy,
    UsageCounter,
    User,
)
from .receipts import reconcile_receipt
from .serializers import SearchSerializer
from .services import IdempotencyConflict, create_draft, create_workspace
from .test_jobs import fixture
from .usage import release_usage, settle_usage

# Disposable synthetic verifier only. No live keys or provider configuration.
KEY = b"synthetic-receipt-test-key-0000000000000000"
VERIFIERS = {"fixture": {"test": KEY}, "fixture2": {"test": KEY}}


def proof(operation, **changes):
    data = {
        "version": 1,
        "key_id": "test",
        "receipt_ref": f"receipt:{operation.id}",
        "operation_id": str(operation.id),
        "workspace_id": str(operation.workspace_id),
        "job_id": str(operation.job_id),
        "source_code": operation.source_code,
        "provider_key": str(operation.provider_key),
        "request_hash": operation.request_hash,
        "policy_fingerprint": operation.policy_fingerprint,
        "outcome": "success",
        "provider_calls": 1,
        "issued_at": int(timezone.now().timestamp()),
    }
    data.update(changes)
    body = json.dumps(data, sort_keys=True).encode()
    return body, hmac.new(KEY, body, hashlib.sha256).hexdigest()


def started():
    user, workspace, job = fixture()
    enqueue_job(user, workspace.id, job.id, 0)
    intent = JobOutbox.objects.get(job=job)
    attempt = claim_pre_dispatch(intent.id)
    return user, workspace, job, intent, begin_dispatch(intent.id, attempt.token)[0]


@override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
class ReceiptTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job, self.intent, self.operation = started()

    def record(self, **changes):
        return reconcile_receipt(
            self.user, self.workspace.id, self.operation.id, *proof(self.operation, **changes)
        )

    def test_success_and_identical_replay_settle_once_without_minting_leads(self):
        body, signature = proof(self.operation)
        first = reconcile_receipt(self.user, self.workspace.id, self.operation.id, body, signature)
        second = reconcile_receipt(self.user, self.workspace.id, self.operation.id, body, signature)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DispatchReceipt.objects.count(), 1)
        self.job.refresh_from_db()
        self.intent.refresh_from_db()
        self.operation.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(
            (self.job.status, self.job.revision, self.job.result_count), ("completed", 3, 0)
        )
        self.assertEqual((self.intent.status, self.operation.status), ("done", "success"))
        self.assertEqual(JobAttempt.objects.get(outbox=self.intent).status, "done")
        self.assertEqual(
            self.intent.reservation.settlement,
            {"leads": 0, "jobs": 1, "provider_calls": 1, "exports": 0},
        )
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 1)
        with self.assertRaises(IdempotencyConflict):
            self.record(receipt_ref="changed")

    def test_noeffect_releases_and_unknown_history_is_preserved(self):
        mark_outcome_unknown(self.user, self.workspace.id, self.operation.id)
        self.operation.refresh_from_db()
        unknown_at = self.operation.unknown_at
        self.record(outcome="noeffect", provider_calls=0)
        self.intent.reservation.refresh_from_db()
        self.operation.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "released")
        self.assertEqual((self.job.status, self.job.result_count), ("failed", 0))
        self.assertEqual(self.operation.unknown_at, unknown_at)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).provider_calls, 0)

    def test_unsigned_unconfigured_malformed_or_unbound_evidence_retains_reservation(self):
        body, signature = proof(self.operation)
        with override_settings(SAAS_RECEIPT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.record()
        for changed in [
            {"provider_key": str(self.intent.id)},
            {"policy_fingerprint": "0" * 64},
            {"provider_calls": True},
            {"provider_calls": 3},
            {"outcome": "noeffect", "provider_calls": 1},
            {"accepted_leads": 10},
            {"issued_at": 0},
            {"issued_at": int(timezone.now().timestamp()) + 10000},
        ]:
            with self.assertRaises(ValidationError):
                self.record(**changed)
        for bad, sig in [(body + b" ", signature), (b"x" * 8193, signature), (body, "0" * 64)]:
            with self.assertRaises(ValidationError):
                reconcile_receipt(self.user, self.workspace.id, self.operation.id, bad, sig)
        self.assertFalse(DispatchReceipt.objects.exists())
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "reserved")

    def test_member_viewer_revocation_and_foreign_operation_are_denied(self):
        membership = Membership.objects.get(workspace=self.workspace, user=self.user)
        for role in ["member", "viewer"]:
            membership.role = role
            membership.save()
            with self.assertRaises(PermissionDenied):
                self.record()
        membership.role = "owner"
        membership.save()
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(Http404):
            reconcile_receipt(self.user, other.id, self.operation.id, *proof(self.operation))
        membership.delete()
        with self.assertRaises(Http404):
            self.record()
        self.assertFalse(DispatchReceipt.objects.exists())

    def test_generic_usage_cannot_bypass_job_reconciliation(self):
        with self.assertRaises(ValidationError):
            release_usage(self.user, self.workspace.id, self.intent.reservation_id)
        with self.assertRaises(ValidationError):
            settle_usage(self.user, self.workspace.id, self.intent.reservation_id, {})
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.intent.reservation.status, "reserved")

    def test_failed_finalization_rolls_back_receipt_operation_and_accounting(self):
        with patch("core.receipts._settle_locked", side_effect=IntegrityError("injected")):
            with self.assertRaises(IntegrityError):
                self.record()
        self.assertFalse(DispatchReceipt.objects.exists())
        self.operation.refresh_from_db()
        self.job.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.operation.status, "started")
        self.assertEqual((self.job.status, self.intent.reservation.status), ("running", "reserved"))

    def test_partial_source_proof_cannot_release_unresolved_effects(self):
        policy = SourcePolicy.objects.get(code="fixture")
        policy.pk = "fixture2"
        policy.save()
        workspace = create_workspace(self.user, {"name": "Multiple sources", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=20, job_limit=2, provider_call_limit=4
        )
        payload = dict(self.job.search, source_codes=["fixture", "fixture2"])
        serializer = SearchSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        job, _ = create_draft(self.user, workspace.id, serializer.validated_data, "multiple")
        enqueue_job(self.user, workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        attempt = claim_pre_dispatch(intent.id)
        first, second = begin_dispatch(intent.id, attempt.token)
        reconcile_receipt(
            self.user, workspace.id, first.id, *proof(first, outcome="noeffect", provider_calls=0)
        )
        intent.reservation.refresh_from_db()
        self.assertEqual(intent.reservation.status, "reserved")
        reconcile_receipt(self.user, workspace.id, second.id, *proof(second))
        intent.reservation.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual((intent.reservation.status, job.status), ("settled", "completed"))
        self.assertEqual(intent.reservation.settlement["provider_calls"], 1)

    def test_source_event_reference_cannot_be_rebound(self):
        self.record(receipt_ref="collision")
        job, _ = create_draft(self.user, self.workspace.id, self.job.search, "second-job")
        enqueue_job(self.user, self.workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        attempt = claim_pre_dispatch(intent.id)
        operation = begin_dispatch(intent.id, attempt.token)[0]
        with self.assertRaises(IdempotencyConflict):
            reconcile_receipt(
                self.user,
                self.workspace.id,
                operation.id,
                *proof(operation, receipt_ref="collision"),
            )
        intent.reservation.refresh_from_db()
        self.assertEqual(intent.reservation.status, "reserved")
        self.assertEqual(DispatchReceipt.objects.count(), 1)

    def test_receipt_migration_reverse_guard(self):
        guard = importlib.import_module(
            "core.migrations.0009_terminal_receipts"
        ).protect_receipt_rollback
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))
        self.record()
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))
        self.assertEqual(DispatchReceipt.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "Receipt races require real PostgreSQL locks")
@override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
class ConcurrentReceiptTests(TransactionTestCase):
    def setUp(self):
        self.user, self.workspace, self.job, self.intent, self.operation = started()

    def race(self, payloads):
        barrier = Barrier(2)

        def run(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                reconcile_receipt(
                    User.objects.get(pk=self.user.id),
                    self.workspace.id,
                    self.operation.id,
                    *payload,
                )
                return "accepted"
            except IdempotencyConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, payloads))

    def test_duplicate_receipts_settle_once(self):
        payload = proof(self.operation)
        self.assertEqual(self.race([payload, payload]), ["accepted", "accepted"])
        self.assertEqual(DispatchReceipt.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).jobs, 1)

    def test_conflicting_terminal_receipts_cannot_double_settle_or_refund(self):
        self.assertCountEqual(
            self.race(
                [proof(self.operation), proof(self.operation, outcome="noeffect", provider_calls=0)]
            ),
            ["accepted", "conflict"],
        )
        self.assertEqual(DispatchReceipt.objects.count(), 1)
        self.intent.reservation.refresh_from_db()
        self.assertIn(self.intent.reservation.status, ["settled", "released"])
        self.assertEqual(
            UsageCounter.objects.get(workspace=self.workspace).jobs,
            int(self.intent.reservation.status == "settled"),
        )
