"""Atomic v3 reconciliation commits only current explicit source outcomes."""

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .attempts import claim_pre_dispatch
from .batch_allocation import allocate_result_batch
from .batch_events import record_batch_candidates
from .batch_noeffect_events import record_source_batch_noeffect
from .batch_reconciliation_settlement import settle_reconciled_batch_job
from .batch_result_pages import batch_results_page
from .batch_settlement_replay import replay_settled_batch_job
from .batch_terminal_events import record_source_batch_terminal
from .dispatch import begin_dispatch
from .jobs import RevisionConflict, enqueue_job
from .models import (
    DispatchOperation,
    Entitlement,
    Job,
    JobOutbox,
    ResultBatch,
    SourceBatchNoEffect,
    SourcePolicy,
    UsageCounter,
    UsageReservation,
)
from .serializers import SearchSerializer
from .services import IdempotencyConflict
from .test_batch_candidates import BatchCandidateTests
from .test_batch_events import KEY as CANDIDATE_KEY
from .test_batch_intake import IntakeFixture
from .test_batch_noeffect_manifest import KEY as ZERO_KEY
from .test_batch_reconciliation_read import FLAGS, NoEffectReconciliationReadTests
from .test_batch_terminal_events import TerminalFixture
from .test_jobs import fixture as job_fixture


@override_settings(**FLAGS, SAAS_BATCH_RECONCILIATION_SETTLEMENT_ENABLED=True)
class PositiveSettlementTests(TerminalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.terminal()

    def settle(self):
        return settle_reconciled_batch_job(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof()},
        )

    def test_explicit_unknown_positive_commits_once(self):
        with override_settings(SAAS_BATCH_RECONCILIATION_SETTLEMENT_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.settle()
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        job, created = self.settle()
        self.assertTrue(created)
        self.assertEqual((job.status, job.result_count), ("completed", 1))
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(
            reservation.settlement, {"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 0}
        )
        with self.assertRaises(RevisionConflict):
            self.settle()
        self.assertEqual(UsageCounter.objects.get(workspace_id=self.operation.workspace_id).jobs, 1)

    def test_late_failure_rolls_back_counter_and_states(self):
        with patch.object(Job, "save", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.settle()
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )
        self.assertEqual(UsageCounter.objects.get(workspace_id=self.operation.workspace_id).jobs, 0)
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "started")


@override_settings(**FLAGS, SAAS_BATCH_RECONCILIATION_SETTLEMENT_ENABLED=True)
class NoEffectSettlementTests(NoEffectReconciliationReadTests):
    def test_explicit_zero_effect_keeps_original_reservation_without_inferred_charge(self):
        proof = self.proof()
        record_source_batch_noeffect(
            self.user, self.operation.workspace_id, self.operation.pk, *proof
        )
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        with self.assertRaises(RevisionConflict):
            settle_reconciled_batch_job(
                self.user,
                self.operation.workspace_id,
                self.operation.job_id,
                {self.operation.pk: proof},
            )
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(reservation.status, "reserved")
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "unknown")


@override_settings(
    **{
        **FLAGS,
        "SAAS_BATCH_ENROLLMENT_SOURCES": frozenset({"fixture", "fixture2"}),
        "SAAS_BATCH_NOEFFECT_VERIFIERS": {"fixture2": {"zero": ZERO_KEY}},
    },
    SAAS_BATCH_RECONCILIATION_SETTLEMENT_ENABLED=True,
)
class MixedSettlementTests(TestCase):
    manifest = IntakeFixture.manifest

    def setUp(self):
        self.user, workspace, job = job_fixture()
        Entitlement.objects.filter(workspace=workspace).update(provider_call_limit=4)
        second = SourcePolicy.objects.get(pk="fixture")
        second.pk = "fixture2"
        second.save(force_insert=True)
        pure = BatchCandidateTests()
        pure.setUp()
        for source in ("fixture", "fixture2"):
            policy = SourcePolicy.objects.get(pk=source)
            policy.controls["result_contract"] = pure.policy.controls["result_contract"]
            policy.save()
        job.search["source_codes"] = ["fixture", "fixture2"]
        serializer = SearchSerializer(data=job.search)
        serializer.is_valid(raise_exception=True)
        job.search = serializer.validated_data
        job.request_hash = hashlib.sha256(
            json.dumps(job.search, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        job.save(update_fields=["search", "request_hash"])
        enqueue_job(self.user, workspace.pk, job.pk, 0)
        intent = JobOutbox.objects.get(job=job)
        attempt = claim_pre_dispatch(intent.pk)
        operations = begin_dispatch(intent.pk, attempt.token)
        JobOutbox.objects.filter(pk=intent.pk).update(result_protocol=3)
        self.operation = next(op for op in operations if op.source_code == "fixture")
        self.zero_operation = next(op for op in operations if op.source_code == "fixture2")
        self.batch, _ = allocate_result_batch(self.user, workspace.pk, self.operation.pk, 1)
        self.zero_batch, _ = allocate_result_batch(
            self.user, workspace.pk, self.zero_operation.pk, 1
        )
        self.candidate = pure.data
        self.candidate.update(
            workspace_id=str(workspace.pk),
            job_id=str(job.pk),
            operation_id=str(self.operation.pk),
            batch_id=str(self.batch.pk),
            provider_key=str(self.operation.provider_key),
            request_hash=self.operation.request_hash,
            policy_fingerprint=self.operation.policy_fingerprint,
        )
        self.namespace = f"saas-results/v1/{workspace.pk}"
        self.dedupe_settings = override_settings(
            SAAS_BATCH_DEDUPE_VERIFIERS={self.namespace: {"dedupe": manifests.DEDUPE}}
        )
        self.dedupe_settings.enable()
        self.addCleanup(self.dedupe_settings.disable)
        self.candidate_body = json.dumps(self.candidate, sort_keys=True).encode()
        self.candidate_signature = hmac.new(
            CANDIDATE_KEY, self.candidate_body, hashlib.sha256
        ).hexdigest()
        record_batch_candidates(
            self.user, workspace.pk, self.batch.pk, self.candidate_body, self.candidate_signature
        )
        self.acceptance, _ = IntakeFixture.intake(self)
        self.issued_at = self.candidate["issued_at"]
        self.terminal_proof_value = TerminalFixture.terminal_proof(self)
        record_source_batch_terminal(
            self.user, workspace.pk, self.operation.pk, *self.terminal_proof_value
        )

    def zero_proof(self):
        op = self.zero_operation
        body = json.dumps(
            {
                "version": 3,
                "kind": "source-noeffect",
                "workspace_id": str(op.workspace_id),
                "job_id": str(op.job_id),
                "operation_id": str(op.pk),
                "provider_key": str(op.provider_key),
                "source_code": op.source_code,
                "request_hash": op.request_hash,
                "policy_fingerprint": op.policy_fingerprint,
                "source_key_id": "zero",
                "receipt_ref": "zero-mixed",
                "issued_at": self.issued_at,
                "provider_calls": 0,
                "batches": [{"batch_id": str(self.zero_batch.pk), "candidate_body_hash": None}],
            }
        ).encode()
        return body, hmac.new(ZERO_KEY, body, hashlib.sha256).hexdigest()

    def test_positive_and_explicit_noeffect_commit_together(self):
        zero_proof = self.zero_proof()
        record_source_batch_noeffect(
            self.user, self.zero_operation.workspace_id, self.zero_operation.pk, *zero_proof
        )
        DispatchOperation.objects.filter(pk=self.zero_operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        job, created = settle_reconciled_batch_job(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof_value, self.zero_operation.pk: zero_proof},
        )
        self.assertTrue(created)
        self.assertEqual((job.status, job.result_count), ("completed", 1))
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).settlement,
            {"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 0},
        )
        self.assertEqual(DispatchOperation.objects.get(pk=self.operation.pk).status, "success")
        self.assertEqual(
            DispatchOperation.objects.get(pk=self.zero_operation.pk).status, "noeffect"
        )

    def test_missing_zero_effect_or_revoked_key_preserves_full_reservation(self):
        zero_proof = self.zero_proof()
        proofs = {self.operation.pk: self.terminal_proof_value, self.zero_operation.pk: zero_proof}
        with self.assertRaises(RevisionConflict):
            settle_reconciled_batch_job(
                self.user, self.operation.workspace_id, self.operation.job_id, proofs
            )
        record_source_batch_noeffect(
            self.user, self.zero_operation.workspace_id, self.zero_operation.pk, *zero_proof
        )
        with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                settle_reconciled_batch_job(
                    self.user, self.operation.workspace_id, self.operation.job_id, proofs
                )
        self.assertEqual(
            UsageReservation.objects.get(pk=self.operation.outbox.reservation_id).status,
            "reserved",
        )
        self.assertEqual(UsageCounter.objects.get(workspace_id=self.operation.workspace_id).jobs, 0)

    def test_mixed_settlement_page_reads_positive_and_rejects_zero_evidence_drift(self):
        zero_proof = self.zero_proof()
        record_source_batch_noeffect(
            self.user, self.zero_operation.workspace_id, self.zero_operation.pk, *zero_proof
        )
        settle_reconciled_batch_job(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof_value, self.zero_operation.pk: zero_proof},
        )
        with override_settings(
            SAAS_BATCH_PAGE_READ_ENABLED=True,
            SAAS_BATCH_PAGE_SIGNING_KEY="test-page-key-with-at-least-32-bytes",
        ):
            page = batch_results_page(self.user, self.operation.workspace_id, self.operation.job_id)
            self.assertEqual(len(page["results"]), 1)
            self.assertEqual(page["results"][0]["source_code"], "fixture")
            SourceBatchNoEffect.objects.filter(operation=self.zero_operation).update(
                batch_set_hash="0" * 64
            )
            with self.assertRaises(RevisionConflict):
                batch_results_page(self.user, self.operation.workspace_id, self.operation.job_id)
            event = SourceBatchNoEffect.objects.get(operation=self.zero_operation)
            event.batch_set_hash = hashlib.sha256(
                json.dumps(
                    [{"batch_id": str(self.zero_batch.pk), "candidate_body_hash": None}],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("ascii")
            ).hexdigest()
            event.save(update_fields=["batch_set_hash"])
            ResultBatch.objects.filter(pk=self.zero_batch.pk).update(ordinal=2)
            with self.assertRaises(RevisionConflict):
                batch_results_page(self.user, self.operation.workspace_id, self.operation.job_id)
            ResultBatch.objects.filter(pk=self.zero_batch.pk).update(ordinal=1)
            SourceBatchNoEffect.objects.filter(operation=self.zero_operation).update(batch_count=2)
            with self.assertRaises(RevisionConflict):
                batch_results_page(self.user, self.operation.workspace_id, self.operation.job_id)

    def test_mixed_settled_replay_checks_fresh_proofs_without_second_charge(self):
        zero_proof = self.zero_proof()
        record_source_batch_noeffect(
            self.user, self.zero_operation.workspace_id, self.zero_operation.pk, *zero_proof
        )
        proofs = {self.operation.pk: self.terminal_proof_value, self.zero_operation.pk: zero_proof}
        settle_reconciled_batch_job(
            self.user, self.operation.workspace_id, self.operation.job_id, proofs
        )
        args = (self.user, self.operation.workspace_id, self.operation.job_id, proofs)
        with override_settings(SAAS_BATCH_SETTLED_REPLAY_ENABLED=True):
            with self.assertRaises(PermissionDenied):
                replay_settled_batch_job(*args)
        with override_settings(
            SAAS_BATCH_SETTLED_REPLAY_ENABLED=True,
            SAAS_BATCH_MIXED_SETTLED_REPLAY_ENABLED=True,
        ):
            job, created = replay_settled_batch_job(*args)
            self.assertFalse(created)
            self.assertEqual(job.status, "completed")
            with self.assertRaises(ValidationError):
                replay_settled_batch_job(
                    *args[:3], {**proofs, self.zero_operation.pk: (zero_proof[0], "0" * 64)}
                )
            with override_settings(SAAS_BATCH_NOEFFECT_VERIFIERS={}):
                with self.assertRaises(ValidationError):
                    replay_settled_batch_job(*args)
            SourceBatchNoEffect.objects.filter(operation=self.zero_operation).update(
                batch_set_hash="0" * 64
            )
            with self.assertRaises(IdempotencyConflict):
                replay_settled_batch_job(*args)
        self.assertEqual(UsageCounter.objects.get(workspace_id=self.operation.workspace_id).jobs, 1)
