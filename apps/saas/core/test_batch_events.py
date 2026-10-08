import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_candidates as pure_fixtures
from .attempts import claim_pre_dispatch
from .batch_allocation import allocate_result_batch
from .batch_events import record_batch_candidates
from .dispatch import begin_dispatch
from .jobs import enqueue_job
from .models import BatchCandidateEvidence, DispatchOperation, JobOutbox, SourcePolicy
from .services import IdempotencyConflict
from .test_jobs import fixture as job_fixture

KEY = pure_fixtures.KEY

SETTINGS = {
    "SAAS_BATCH_ALLOCATION_ENABLED": True,
    "SAAS_BATCH_CANDIDATE_EVENTS_ENABLED": True,
    "SAAS_BATCH_ENROLLMENT_SOURCES": frozenset({"fixture"}),
    "SAAS_BATCH_CANDIDATE_VERIFIERS": {"fixture": {"candidate": KEY}},
}


def fixture():
    pure = pure_fixtures.BatchCandidateTests()
    pure.setUp()
    user, workspace, job = job_fixture()
    policy = SourcePolicy.objects.get(pk="fixture")
    policy.controls["result_contract"] = deepcopy(pure.policy.controls["result_contract"])
    policy.save()
    enqueue_job(user, workspace.id, job.id, 0)
    intent = JobOutbox.objects.get(job=job)
    attempt = claim_pre_dispatch(intent.pk)
    operation = begin_dispatch(intent.pk, attempt.token)[0]
    # Synthetic future started context only; runtime v3 start stays quarantined.
    JobOutbox.objects.filter(pk=intent.pk).update(result_protocol=3)
    batch, _ = allocate_result_batch(user, workspace.pk, operation.pk, 1)
    data = pure.data
    data.update(
        workspace_id=str(workspace.pk),
        job_id=str(job.pk),
        operation_id=str(operation.pk),
        batch_id=str(batch.pk),
        provider_key=str(operation.provider_key),
        request_hash=operation.request_hash,
        policy_fingerprint=operation.policy_fingerprint,
    )
    return user, operation, batch, data


def signed(data):
    raw = json.dumps(data, sort_keys=True).encode()
    return raw, hmac.new(KEY, raw, hashlib.sha256).hexdigest()


@override_settings(**SETTINGS)
class BatchEventTests(TestCase):
    def setUp(self):
        self.user, self.operation, self.batch, self.data = fixture()

    def record(self, data=None, batch=None):
        return record_batch_candidates(
            self.user,
            self.operation.workspace_id,
            (batch or self.batch).pk,
            *signed(self.data if data is None else data),
        )

    def test_disabled_service_and_invalid_proof_make_no_event(self):
        with (
            override_settings(SAAS_BATCH_CANDIDATE_EVENTS_ENABLED=False),
            self.assertRaises(PermissionDenied),
        ):
            self.record()
        with self.assertRaises(ValidationError):
            self.record({**self.data, "batch_id": "foreign"})
        self.assertFalse(BatchCandidateEvidence.objects.exists())

    def test_exact_replay_redacted_event_and_capacity_preserved(self):
        first, created = self.record()
        same, replay = self.record()
        self.assertTrue(created)
        self.assertFalse(replay)
        self.assertEqual(first.pk, same.pk)
        self.assertFalse(hasattr(first, "records"))
        self.operation.outbox.reservation.refresh_from_db()
        self.operation.job.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
        self.assertEqual(self.operation.job.result_count, 0)
        self.assertFalse(self.operation.job.acceptedresult_set.exists())

    def test_changed_body_conflicts_and_cross_batch_reference_cannot_replay(self):
        self.record()
        with self.assertRaises(IdempotencyConflict):
            self.record({**self.data, "event_ref": "changed"})
        second, _ = allocate_result_batch(
            self.user, self.operation.workspace_id, self.operation.pk, 2
        )
        with self.assertRaises(IdempotencyConflict):
            self.record({**self.data, "batch_id": str(second.pk)}, second)
        self.assertEqual(BatchCandidateEvidence.objects.count(), 1)

    def test_unknown_can_replay_only_existing_event_and_never_refund(self):
        first, _ = self.record()
        second, _ = allocate_result_batch(
            self.user, self.operation.workspace_id, self.operation.pk, 2
        )
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        self.assertEqual(self.record()[0].pk, first.pk)
        with self.assertRaises(ValidationError):
            self.record({**self.data, "batch_id": str(second.pk), "event_ref": "second"}, second)

    def test_transactional_event_failure_keeps_original_identity_without_payload(self):
        with (
            patch(
                "core.batch_events.BatchCandidateEvidence.objects.create",
                side_effect=IntegrityError("injected"),
            ),
            self.assertRaises(IdempotencyConflict),
        ):
            self.record()
        self.assertFalse(BatchCandidateEvidence.objects.exists())
        self.batch.refresh_from_db()
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")

    def test_replay_rechecks_revoked_keys_and_current_source_rights(self):
        self.record()
        with (
            override_settings(SAAS_BATCH_CANDIDATE_VERIFIERS={}),
            self.assertRaises(ValidationError),
        ):
            self.record()
        SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
        with self.assertRaises(PermissionDenied):
            self.record()


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL candidate-event races required")
@override_settings(**SETTINGS)
class BatchEventRaceTests(TransactionTestCase):
    def setUp(self):
        self.user, self.operation, self.batch, self.data = fixture()

    def race(self, data):
        barrier = Barrier(2)

        def run(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return record_batch_candidates(
                    self.user, self.operation.workspace_id, self.batch.pk, *signed(payload)
                )[1]
            except IdempotencyConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, data))

    def test_duplicate_event_creates_once_and_exact_replays(self):
        self.assertCountEqual(self.race([self.data, self.data]), [True, False])
        self.assertEqual(BatchCandidateEvidence.objects.count(), 1)

    def test_changed_event_bytes_commit_once_and_conflict(self):
        self.assertCountEqual(
            self.race([self.data, {**self.data, "event_ref": "changed"}]), [True, "conflict"]
        )
        self.assertEqual(BatchCandidateEvidence.objects.count(), 1)
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
