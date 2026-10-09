"""Read-only source replay preserves reserved and unknown operation states."""

import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .batch_noeffect_events import record_source_batch_noeffect
from .batch_reconciliation_read import inspect_batch_reconciliation
from .jobs import RevisionConflict
from .models import DispatchOperation, UsageCounter, UsageReservation
from .services import IdempotencyConflict
from .test_batch_events import SETTINGS
from .test_batch_intake import IntakeFixture
from .test_batch_noeffect_manifest import KEY as ZERO_KEY
from .test_batch_terminal_events import TERMINAL_KEY, TerminalFixture

FLAGS = dict(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_TERMINAL_EVENTS_ENABLED=True,
    SAAS_BATCH_TERMINAL_VERIFIERS={"fixture": {"terminal": TERMINAL_KEY}},
    SAAS_BATCH_NOEFFECT_EVENTS_ENABLED=True,
    SAAS_BATCH_NOEFFECT_VERIFIERS={"fixture": {"zero": ZERO_KEY}},
    SAAS_BATCH_RECONCILIATION_READ_ENABLED=True,
)


@override_settings(**FLAGS)
class PositiveReconciliationReadTests(TerminalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.terminal()

    def inspect(self, proofs=None):
        return inspect_batch_reconciliation(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof()} if proofs is None else proofs,
        )

    def test_positive_source_is_read_only_and_requires_exact_record(self):
        with override_settings(SAAS_BATCH_RECONCILIATION_READ_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.inspect()
        first = self.inspect()
        second = self.inspect()
        self.assertEqual(first, second)
        self.assertEqual((first.leads, first.provider_calls), (1, 1))
        self.assertEqual(first.positive_operation_ids, (self.operation.pk,))
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )
        self.assertEqual(
            UsageCounter.objects.get(workspace_id=self.operation.workspace_id).jobs, 0
        )

    def test_changed_proof_or_missing_original_source_fails(self):
        with self.assertRaises(RevisionConflict):
            self.inspect({})
        with self.assertRaises(IdempotencyConflict):
            self.inspect({self.operation.pk: self.terminal_proof({"receipt_ref": "changed"})})


@override_settings(**FLAGS)
class NoEffectReconciliationReadTests(IntakeFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.issued_at = int(timezone.now().timestamp())

    def proof(self, **changes):
        op = self.operation
        data = dict(
            version=3,
            kind="source-noeffect",
            workspace_id=str(op.workspace_id),
            job_id=str(op.job_id),
            operation_id=str(op.pk),
            provider_key=str(op.provider_key),
            source_code=op.source_code,
            request_hash=op.request_hash,
            policy_fingerprint=op.policy_fingerprint,
            source_key_id="zero",
            receipt_ref="zero-read",
            issued_at=self.issued_at,
            provider_calls=0,
            batches=[
                {
                    "batch_id": str(self.batch.pk),
                    "candidate_body_hash": hashlib.sha256(self.candidate_body).hexdigest(),
                }
            ],
        )
        data.update(changes)
        body = json.dumps(data).encode()
        return body, hmac.new(ZERO_KEY, body, hashlib.sha256).hexdigest()

    def inspect(self, proof=None):
        return inspect_batch_reconciliation(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.proof() if proof is None else proof},
        )

    def test_unknown_zero_effect_is_explicit_and_does_not_release_reservation(self):
        with self.assertRaises(RevisionConflict):
            self.inspect()
        proof = self.proof()
        record_source_batch_noeffect(
            self.user, self.operation.workspace_id, self.operation.pk, *proof
        )
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        result = self.inspect(proof)
        self.assertEqual((result.leads, result.provider_calls), (0, 0))
        self.assertEqual(result.noeffect_operation_ids, (self.operation.pk,))
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "unknown")

    def test_revoked_noeffect_authority_denies_read(self):
        proof = self.proof()
        record_source_batch_noeffect(
            self.user, self.operation.workspace_id, self.operation.pk, *proof
        )
        with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.inspect(proof)
