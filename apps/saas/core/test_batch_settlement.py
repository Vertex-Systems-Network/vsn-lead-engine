"""Default-off v3 settlement commits only exact all-source positive use."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .batch_settlement import settle_batch_job
from .batch_settlement_replay import replay_settled_batch_job
from .jobs import RevisionConflict
from .models import BatchAcceptance, DispatchOperation, Job, SourcePolicy, UsageCounter, UsageReservation
from .services import IdempotencyConflict
from .test_batch_events import SETTINGS
from .test_batch_terminal_events import TERMINAL_KEY, TerminalFixture


@override_settings(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_TERMINAL_EVENTS_ENABLED=True,
    SAAS_BATCH_SETTLEMENT_ENABLED=True,
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_TERMINAL_VERIFIERS={"fixture": {"terminal": TERMINAL_KEY}},
)
class BatchSettlementTests(TerminalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.terminal()

    def settle(self, changes=None):
        return settle_batch_job(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof(changes)},
        )

    def test_default_gate_then_atomic_positive_settlement(self):
        with override_settings(SAAS_BATCH_SETTLEMENT_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.settle()
        result, created = self.settle()
        self.assertTrue(created)
        self.assertEqual((result.status, result.result_count), ("completed", 1))
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(reservation.status, "settled")
        self.assertEqual(
            reservation.settlement,
            {"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 0},
        )
        counter = UsageCounter.objects.get(workspace_id=self.operation.workspace_id)
        self.assertEqual((counter.leads, counter.jobs, counter.provider_calls), (1, 1, 1))
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "success")
        with self.assertRaises(RevisionConflict):
            self.settle()
        counter.refresh_from_db()
        self.assertEqual((counter.leads, counter.jobs, counter.provider_calls), (1, 1, 1))

    def test_replay_revocation_and_batch_evidence_drift_fail_closed(self):
        self.settle()
        args = (
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof()},
        )
        with override_settings(SAAS_BATCH_SETTLED_REPLAY_ENABLED=True):
            SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
            with self.assertRaises(PermissionDenied):
                replay_settled_batch_job(*args)
            SourcePolicy.objects.filter(pk="fixture").update(enabled=True)
            BatchAcceptance.objects.filter(candidate__batch=self.batch).update(body_hash="b" * 64)
            with self.assertRaises(ValidationError):
                replay_settled_batch_job(*args)

    def test_changed_or_missing_final_proofs_do_not_settle(self):
        with self.assertRaises(IdempotencyConflict):
            self.settle({"receipt_ref": "changed"})
        with self.assertRaises(RevisionConflict):
            settle_batch_job(self.user, self.operation.workspace_id, self.operation.job_id, {})
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )

    def test_unknown_effect_is_never_inferred_safe(self):
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        with self.assertRaises(RevisionConflict):
            self.settle()
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )

    def test_post_settlement_write_failure_rolls_back_usage_and_state(self):
        with patch.object(Job, "save", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.settle()
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )
        counter = UsageCounter.objects.get(workspace_id=self.operation.workspace_id)
        self.assertEqual((counter.leads, counter.jobs, counter.provider_calls), (0, 0, 0))
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "started")

    def test_separate_settled_replay_checks_current_proof_without_double_charge(self):
        self.settle()
        args = (
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof()},
        )
        with self.assertRaises(PermissionDenied):
            replay_settled_batch_job(*args)
        with override_settings(SAAS_BATCH_SETTLED_REPLAY_ENABLED=True):
            job, created = replay_settled_batch_job(*args)
            self.assertFalse(created)
            self.assertEqual(job.status, "completed")
            with self.assertRaises(IdempotencyConflict):
                replay_settled_batch_job(
                    *args[:3], {self.operation.pk: self.terminal_proof({"receipt_ref": "changed"})}
                )
            with self.assertRaises(RevisionConflict):
                replay_settled_batch_job(*args[:3], {})
            with override_settings(SAAS_BATCH_TERMINAL_VERIFIERS={}):
                with self.assertRaises(ValidationError):
                    replay_settled_batch_job(*args)
        counter = UsageCounter.objects.get(workspace_id=self.operation.workspace_id)
        self.assertEqual((counter.leads, counter.jobs, counter.provider_calls), (1, 1, 1))
