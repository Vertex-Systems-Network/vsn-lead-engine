"""Source-final metadata never turns partial or unknown batches into settled use."""

import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .batch_terminal_events import record_source_batch_terminal
from .models import DispatchOperation, SourceBatchTerminal, UsageReservation
from .services import IdempotencyConflict
from .test_batch_events import SETTINGS
from .test_batch_intake import IntakeFixture, manifests
from .test_terminal_manifest import KEY as TERMINAL_KEY


class TerminalFixture(IntakeFixture):
    def setUp(self):
        super().setUp()
        self.acceptance, _ = self.intake()

    def terminal_proof(self, changes=None):
        operation = self.operation
        data = {
            "workspace_id": str(operation.workspace_id),
            "job_id": str(operation.job_id),
            "operation_id": str(operation.pk),
            "provider_key": str(operation.provider_key),
            "source_code": operation.source_code,
            "request_hash": operation.request_hash,
            "policy_fingerprint": operation.policy_fingerprint,
            "version": 3,
            "kind": "source-final",
            "source_key_id": "terminal",
            "receipt_ref": "final-1",
            "issued_at": self.candidate["issued_at"],
            "provider_calls": 1,
            "batches": [
                {
                    "batch_id": str(self.batch.pk),
                    "acceptance_body_hash": self.acceptance.body_hash,
                    "accepted_count": 1,
                    "provider_calls": 1,
                }
            ],
        }
        data.update(changes or {})
        body = json.dumps(data).encode()
        return body, hmac.new(TERMINAL_KEY, body, hashlib.sha256).hexdigest()

    def terminal(self, changes=None):
        body, signature = self.terminal_proof(changes)
        return record_source_batch_terminal(
            self.user,
            self.operation.workspace_id,
            self.operation.pk,
            body,
            signature,
        )


@override_settings(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_TERMINAL_EVENTS_ENABLED=True,
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_TERMINAL_VERIFIERS={"fixture": {"terminal": TERMINAL_KEY}},
)
class TerminalEventTests(TerminalFixture, TestCase):
    def test_default_gate_exact_replay_and_no_settlement(self):
        with override_settings(SAAS_BATCH_TERMINAL_EVENTS_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.terminal()
        first, created = self.terminal()
        second, replay = self.terminal()
        self.assertTrue(created)
        self.assertFalse(replay)
        self.assertEqual(first.pk, second.pk)
        self.operation.job.refresh_from_db()
        self.assertEqual(self.operation.job.result_count, 0)
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(reservation.status, "reserved")

    def test_unaccepted_allocation_blocks_source_final_without_accounting(self):
        allocate_result_batch(self.user, self.operation.workspace_id, self.operation.pk, 2)
        with self.assertRaises(ValidationError):
            self.terminal()
        self.assertFalse(SourceBatchTerminal.objects.exists())

    def test_changed_signed_finality_conflicts_and_revocation_blocks_replay(self):
        self.terminal()
        with self.assertRaises(IdempotencyConflict):
            self.terminal({"receipt_ref": "changed"})
        with override_settings(SAAS_BATCH_TERMINAL_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.terminal()
        self.assertEqual(SourceBatchTerminal.objects.count(), 1)

    def test_unknown_effect_requires_existing_exact_source_final(self):
        first, _ = self.terminal()
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        replay, created = self.terminal()
        self.assertFalse(created)
        self.assertEqual(replay.pk, first.pk)
        with self.assertRaises(IdempotencyConflict):
            self.terminal({"receipt_ref": "changed"})

    def test_unknown_effect_cannot_create_new_finality(self):
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        with self.assertRaises(ValidationError):
            self.terminal()
        self.assertFalse(SourceBatchTerminal.objects.exists())
