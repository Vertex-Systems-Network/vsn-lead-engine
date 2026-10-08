import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .attempts import claim_pre_dispatch
from .dispatch import begin_dispatch
from .jobs import enqueue_job
from .models import (
    BatchAcceptance,
    BatchCandidateEvidence,
    JobOutbox,
    ResultBatch,
    SourceBatchTerminal,
    UsageCounter,
)
from .test_jobs import fixture


def setup_operation():
    user, workspace, job = fixture()
    enqueue_job(user, workspace.id, job.id, 0)
    outbox = JobOutbox.objects.get(job=job)
    attempt = claim_pre_dispatch(outbox.id)
    return begin_dispatch(outbox.id, attempt.token)[0]


def candidate_values(batch, **changes):
    values = dict(
        batch=batch,
        source_code="fixture",
        event_ref=f"candidate:{batch.id}",
        body_hash="a" * 64,
        candidate_count=1,
        earliest_delete_at=timezone.now() + timedelta(days=1),
    )
    values.update(changes)
    return values


def acceptance_values(candidate, **changes):
    values = dict(
        candidate=candidate,
        source_code="fixture",
        receipt_ref=f"acceptance:{candidate.batch_id}",
        source_key_id="fixture-source",
        dedupe_key_id="fixture-registry",
        body_hash="b" * 64,
        namespace="fixture-isolated",
        accepted_count=1,
        provider_calls=1,
        issued_at=timezone.now(),
    )
    values.update(changes)
    return values


def terminal_values(operation, **changes):
    values = dict(
        operation=operation,
        source_code="fixture",
        receipt_ref=f"terminal:{operation.id}",
        source_key_id="fixture-source",
        body_hash="c" * 64,
        batch_set_hash="d" * 64,
        batch_count=1,
        accepted_count=1,
        provider_calls=1,
        issued_at=timezone.now(),
    )
    values.update(changes)
    return values


class BatchModelTests(TestCase):
    def setUp(self):
        self.operation = setup_operation()

    def batch(self, ordinal=1):
        return ResultBatch.objects.create(operation=self.operation, ordinal=ordinal)

    def reject(self, model, **values):
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(**values)

    def test_identity_is_unique_per_operation_and_ordinal_is_positive(self):
        first = self.batch()
        second = self.batch(2)
        self.assertNotEqual(first.id, second.id)
        self.reject(ResultBatch, operation=self.operation, ordinal=1)
        self.reject(ResultBatch, operation=self.operation, ordinal=0)
        self.assertEqual(ResultBatch.objects.count(), 2)

    def test_candidate_is_once_per_batch_and_reference_once_per_source(self):
        first, second = self.batch(), self.batch(2)
        candidate = BatchCandidateEvidence.objects.create(**candidate_values(first))
        self.reject(BatchCandidateEvidence, **candidate_values(first, event_ref="different"))
        self.reject(
            BatchCandidateEvidence, **candidate_values(second, event_ref=candidate.event_ref)
        )
        BatchCandidateEvidence.objects.create(**candidate_values(second))
        self.assertEqual(BatchCandidateEvidence.objects.count(), 2)

    def test_candidate_count_keeps_twenty_five_row_boundary(self):
        batch = self.batch()
        for count in (0, 26):
            self.reject(BatchCandidateEvidence, **candidate_values(batch, candidate_count=count))
        BatchCandidateEvidence.objects.create(**candidate_values(batch, candidate_count=25))

    def test_acceptance_is_once_per_candidate_and_reference_once_per_source(self):
        first = BatchCandidateEvidence.objects.create(**candidate_values(self.batch()))
        second = BatchCandidateEvidence.objects.create(**candidate_values(self.batch(2)))
        receipt = BatchAcceptance.objects.create(**acceptance_values(first))
        self.reject(BatchAcceptance, **acceptance_values(first, receipt_ref="different"))
        self.reject(BatchAcceptance, **acceptance_values(second, receipt_ref=receipt.receipt_ref))
        BatchAcceptance.objects.create(**acceptance_values(second))
        self.assertEqual(BatchAcceptance.objects.count(), 2)

    def test_acceptance_count_and_calls_are_bounded(self):
        candidate = BatchCandidateEvidence.objects.create(**candidate_values(self.batch()))
        for changes in ({"accepted_count": 0}, {"accepted_count": 26}, {"provider_calls": 0}):
            self.reject(BatchAcceptance, **acceptance_values(candidate, **changes))
        BatchAcceptance.objects.create(**acceptance_values(candidate, accepted_count=25))

    def test_terminal_is_once_per_operation_and_reference_once_per_source(self):
        SourceBatchTerminal.objects.create(**terminal_values(self.operation))
        self.reject(SourceBatchTerminal, **terminal_values(self.operation, receipt_ref="changed"))
        # A distinct operation can exist without manufacturing a second job/tenant.
        operation = self.operation
        operation.pk = None
        import uuid

        operation.provider_key = uuid.uuid4()
        operation.source_code = "second-fixture"
        operation.save(force_insert=True)
        self.reject(
            SourceBatchTerminal,
            **terminal_values(
                operation,
                receipt_ref=f"terminal:{SourceBatchTerminal.objects.first().operation_id}",
            ),
        )

    def test_terminal_counts_require_consistent_zero_or_nonzero_batch_totals(self):
        for changes in (
            {"batch_count": 0, "accepted_count": 1},
            {"batch_count": 2, "accepted_count": 1},
            {"batch_count": 1, "accepted_count": 26},
            {"provider_calls": 0},
        ):
            self.reject(SourceBatchTerminal, **terminal_values(self.operation, **changes))
        SourceBatchTerminal.objects.create(
            **terminal_values(self.operation, batch_count=0, accepted_count=0, provider_calls=0)
        )

    def test_metadata_writes_do_not_accept_payload_or_settle_reserved_usage(self):
        candidate = BatchCandidateEvidence.objects.create(**candidate_values(self.batch()))
        BatchAcceptance.objects.create(**acceptance_values(candidate))
        SourceBatchTerminal.objects.create(**terminal_values(self.operation))
        outbox = self.operation.outbox
        outbox.job.refresh_from_db()
        outbox.reservation.refresh_from_db()
        self.assertEqual((outbox.job.status, outbox.job.result_count), ("running", 0))
        self.assertEqual(outbox.reservation.status, "reserved")
        self.assertEqual(
            list(UsageCounter.objects.values_list("leads", "jobs", "provider_calls")), [(0, 0, 0)]
        )
        self.assertFalse(outbox.job.acceptedresult_set.exists())
        for model in (ResultBatch, BatchCandidateEvidence, BatchAcceptance, SourceBatchTerminal):
            names = {field.name for field in model._meta.fields}
            self.assertTrue(names.isdisjoint({"body", "signature", "records", "fields", "tokens"}))

    def test_protected_links_preserve_identity_and_evidence(self):
        batch = self.batch()
        candidate = BatchCandidateEvidence.objects.create(**candidate_values(batch))
        BatchAcceptance.objects.create(**acceptance_values(candidate))
        for obj in (self.operation, batch, candidate):
            with self.assertRaises(ProtectedError):
                obj.delete()

    def test_reverse_migration_refuses_each_evidence_table(self):
        migration = importlib.import_module("core.migrations.0018_batch_evidence_scaffold")
        editor = SimpleNamespace(connection=connection)
        migration.protect_batch_rollback(apps, editor)
        batch = self.batch()
        with self.assertRaisesRegex(RuntimeError, "preservation plan"):
            migration.protect_batch_rollback(apps, editor)
        candidate = BatchCandidateEvidence.objects.create(**candidate_values(batch))
        BatchAcceptance.objects.create(**acceptance_values(candidate))
        SourceBatchTerminal.objects.create(**terminal_values(self.operation))
        # Isolate each check by mocking only exists on earlier tables; no destructive deletion.
        from unittest.mock import patch

        names = ("ResultBatch", "BatchCandidateEvidence", "BatchAcceptance", "SourceBatchTerminal")
        for index in range(len(names)):
            with patch.object(apps, "get_model") as get_model:
                from unittest.mock import MagicMock

                get_model.side_effect = [
                    MagicMock(**{"objects.using.return_value.exists.return_value": i == index})
                    for i in range(index + 1)
                ]
                with self.assertRaisesRegex(RuntimeError, "preservation plan"):
                    migration.protect_batch_rollback(apps, editor)


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL uniqueness races required")
class BatchModelRaceTests(TransactionTestCase):
    def setUp(self):
        self.operation = setup_operation()
        self.batch = ResultBatch.objects.create(operation=self.operation, ordinal=1)

    def race(self, action):
        barrier = Barrier(2)

        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    action()
                return "created"
            except IntegrityError:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(run, range(2))), ["created", "conflict"])

    def test_duplicate_batch_ordinal_race_commits_once(self):
        self.race(lambda: ResultBatch.objects.create(operation=self.operation, ordinal=2))
        self.assertEqual(ResultBatch.objects.count(), 2)

    def test_duplicate_candidate_reference_race_commits_once(self):
        other = ResultBatch.objects.create(operation=self.operation, ordinal=2)
        barrier_batch = iter([self.batch, other])
        self.race(
            lambda: BatchCandidateEvidence.objects.create(
                **candidate_values(next(barrier_batch), event_ref="shared")
            )
        )
        self.assertEqual(BatchCandidateEvidence.objects.count(), 1)

    def test_duplicate_terminal_race_commits_once_and_retains_reservation(self):
        self.race(lambda: SourceBatchTerminal.objects.create(**terminal_values(self.operation)))
        self.assertEqual(SourceBatchTerminal.objects.count(), 1)
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
