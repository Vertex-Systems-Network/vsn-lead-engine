"""No-effect metadata remains guarded and leaves unknown usage reserved."""

import hashlib
import hmac
import importlib
import json

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .batch_allocation import allocate_result_batch
from .batch_noeffect_events import record_source_batch_noeffect
from .batch_terminal_events import record_source_batch_terminal
from .jobs import RevisionConflict
from .models import SourceBatchNoEffect, UsageCounter
from .services import IdempotencyConflict
from .test_batch_events import SETTINGS
from .test_batch_intake import IntakeFixture
from .test_batch_noeffect_manifest import KEY


@override_settings(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_TERMINAL_EVENTS_ENABLED=True,
    SAAS_BATCH_NOEFFECT_EVENTS_ENABLED=True,
    SAAS_BATCH_NOEFFECT_VERIFIERS={"fixture": {"zero": KEY}},
)
class NoEffectEventTests(IntakeFixture, TestCase):
    def manifest(self, **changes):
        operation = self.operation
        data = {
            "version": 3,
            "kind": "source-noeffect",
            "workspace_id": str(operation.workspace_id),
            "job_id": str(operation.job_id),
            "operation_id": str(operation.pk),
            "provider_key": str(operation.provider_key),
            "source_code": operation.source_code,
            "request_hash": operation.request_hash,
            "policy_fingerprint": operation.policy_fingerprint,
            "source_key_id": "zero",
            "receipt_ref": "zero-1",
            "issued_at": int(timezone.now().timestamp()),
            "provider_calls": 0,
            "batches": [
                {
                    "batch_id": str(self.batch.pk),
                    "candidate_body_hash": hashlib.sha256(self.candidate_body).hexdigest(),
                }
            ],
        }
        data.update(changes)
        body = json.dumps(data).encode()
        return body, hmac.new(KEY, body, hashlib.sha256).hexdigest()

    def record(self, **changes):
        return record_source_batch_noeffect(
            self.user, self.operation.workspace_id, self.operation.pk, *self.manifest(**changes)
        )

    def test_disabled_replay_and_no_accounting(self):
        with override_settings(SAAS_BATCH_NOEFFECT_EVENTS_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.record()
        first, created = self.record()
        replay, again = self.record()
        self.assertTrue(created)
        self.assertFalse(again)
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(first.provider_calls, 0)
        self.assertFalse(hasattr(first, "signature"))
        self.operation.outbox.reservation.refresh_from_db()
        self.operation.job.refresh_from_db()
        self.operation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
        self.assertEqual(self.operation.status, "started")
        self.assertEqual(self.operation.job.result_count, 0)
        self.assertEqual(UsageCounter.objects.get(workspace=self.operation.workspace).leads, 0)

    def test_candidate_and_identity_drift_denied(self):
        with self.assertRaises(ValidationError):
            self.record(batches=[{"batch_id": str(self.batch.pk), "candidate_body_hash": None}])
        other, _ = allocate_result_batch(self.user, self.operation.workspace_id, self.operation.pk, 2)
        with self.assertRaises(ValidationError):
            self.record()
        rows = [
            {
                "batch_id": str(self.batch.pk),
                "candidate_body_hash": hashlib.sha256(self.candidate_body).hexdigest(),
            },
            {"batch_id": str(other.pk), "candidate_body_hash": None},
        ]
        self.record(batches=sorted(rows, key=lambda row: row["batch_id"]))
        with self.assertRaises(IdempotencyConflict):
            self.record(batches=sorted(rows, key=lambda row: row["batch_id"]), receipt_ref="changed")

    def test_existing_acceptance_and_revoked_key_fail_closed(self):
        self.intake()
        with self.assertRaises(ValidationError):
            self.record()
        self.assertFalse(SourceBatchNoEffect.objects.exists())
        with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.record()

    def test_recorded_claim_blocks_new_identity_and_positive_finality(self):
        self.record()
        with self.assertRaises(RevisionConflict):
            allocate_result_batch(self.user, self.operation.workspace_id, self.operation.pk, 2)
        with self.assertRaises(RevisionConflict):
            record_source_batch_terminal(
                self.user, self.operation.workspace_id, self.operation.pk, b"{}", "0" * 64
            )

    def test_key_revocation_and_rollback_guard(self):
        self.record()
        with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.record()
        migration = importlib.import_module("core.migrations.0021_batch_noeffect")
        with self.assertRaises(RuntimeError):
            migration.protect_noeffect_rollback(
                apps, type("Schema", (), {"connection": connection})()
            )

    def test_db_constraints(self):
        first, _ = self.record()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SourceBatchNoEffect.objects.filter(pk=first.pk).update(provider_calls=1)
