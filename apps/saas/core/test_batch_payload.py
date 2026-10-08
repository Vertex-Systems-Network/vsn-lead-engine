"""Schema fixtures only: no v3 service enrollment or signer truth is asserted."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from . import test_accepted_results as legacy
from . import test_batch_models as batch
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    BatchAcceptance,
    BatchCandidateEvidence,
    JobOutbox,
    ResultBatch,
)
from .result_query import results_snapshot
from .result_retention import expire_result_payloads


class PayloadFixture(legacy.AcceptanceFixture):
    def setUp(self):
        super().setUp()
        self.accept()
        self.legacy_row = AcceptedResult.objects.get()
        candidate = BatchCandidateEvidence.objects.create(
            **batch.candidate_values(
                ResultBatch.objects.create(operation=self.operation, ordinal=1)
            )
        )
        self.batch_acceptance = BatchAcceptance.objects.create(**batch.acceptance_values(candidate))

    def row_values(self, **changes):
        row = self.legacy_row
        values = {
            f.name: getattr(row, f.name) for f in AcceptedResult._meta.fields if f.name != "id"
        }
        values.update(
            acceptance=None,
            batch_acceptance=self.batch_acceptance,
            batch_position=1,
            record_ref="synthetic-v3-record",
        )
        values.update(changes)
        return values

    def reject(self, **changes):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcceptedResult.objects.create(**self.row_values(**changes))


class BatchPayloadTests(PayloadFixture, TestCase):
    def test_exactly_one_protocol_link_and_bounded_position_are_required(self):
        for changes in (
            {"batch_acceptance": None},
            {"acceptance": self.legacy_row.acceptance},
            {"batch_position": None},
            {"batch_position": 0},
            {"batch_position": 26},
            {
                "acceptance": self.legacy_row.acceptance,
                "batch_acceptance": None,
                "batch_position": 1,
            },
        ):
            self.reject(**changes)
        row = AcceptedResult.objects.create(**self.row_values())
        self.assertIsNone(row.acceptance_id)
        self.assertEqual(row.batch_position, 1)
        self.legacy_row.refresh_from_db()
        self.assertIsNone(self.legacy_row.batch_acceptance_id)
        self.assertIsNone(self.legacy_row.batch_position)

    def test_reference_and_position_are_unique_per_batch(self):
        AcceptedResult.objects.create(**self.row_values())
        self.reject(batch_position=2)
        self.reject(record_ref="different")
        AcceptedResult.objects.create(**self.row_values(record_ref="different", batch_position=2))
        other = BatchCandidateEvidence.objects.create(
            **batch.candidate_values(
                ResultBatch.objects.create(operation=self.operation, ordinal=2)
            )
        )
        acceptance = BatchAcceptance.objects.create(**batch.acceptance_values(other))
        AcceptedResult.objects.create(**self.row_values(batch_acceptance=acceptance))
        self.assertEqual(AcceptedResult.objects.count(), 4)

    def test_fingerprint_uniqueness_spans_legacy_and_v3_rows(self):
        row = AcceptedResult.objects.create(**self.row_values())
        original = AcceptedFingerprint.objects.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcceptedFingerprint.objects.create(
                workspace=self.workspace, result=row, token=original.token
            )
        AcceptedFingerprint.objects.create(
            workspace=self.workspace, result=row, token="n:" + "9" * 24
        )
        self.assertEqual(AcceptedFingerprint.objects.count(), 4)

    def test_batch_payload_does_not_enter_legacy_visibility_and_v3_intent_is_withheld(self):
        AcceptedResult.objects.create(**self.row_values())
        visible = results_snapshot(self.user, self.workspace.id, self.job.id)["results"]
        self.assertEqual([r["id"] for r in visible], [str(self.legacy_row.id)])
        # Synthetic mixed state: public v2 read fails closed even with a legacy receipt.
        JobOutbox.objects.filter(pk=self.intent.pk).update(result_protocol=3)
        snapshot = results_snapshot(self.user, self.workspace.id, self.job.id)
        self.assertEqual(snapshot["results"], [])
        self.assertFalse(snapshot["can_review_export"])

    def test_erasure_keeps_batch_link_position_fingerprints_and_rollback_guard(self):
        row = AcceptedResult.objects.create(
            **self.row_values(delete_at=timezone.now() - timedelta(seconds=1))
        )
        fingerprint = AcceptedFingerprint.objects.create(
            workspace=self.workspace, result=row, token="n:" + "9" * 24
        )
        self.assertEqual(expire_result_payloads(self.user, self.workspace.id)["erased_count"], 1)
        row.refresh_from_db()
        self.assertEqual((row.fields, row.field_lineage, row.record_ref), ({}, {}, None))
        self.assertEqual(
            (row.batch_acceptance_id, row.batch_position), (self.batch_acceptance.id, 1)
        )
        self.assertTrue(AcceptedFingerprint.objects.filter(pk=fingerprint.pk).exists())
        guard = importlib.import_module(
            "core.migrations.0020_batch_payload_links"
        ).protect_payload_rollback
        with self.assertRaisesRegex(RuntimeError, "preservation plan"):
            guard(apps, SimpleNamespace(connection=connection))
        with self.assertRaises(ProtectedError):
            self.batch_acceptance.delete()

    def test_schema_writes_do_not_change_accounting_and_legacy_allows_reverse_guard(self):
        guard = importlib.import_module(
            "core.migrations.0020_batch_payload_links"
        ).protect_payload_rollback
        guard(apps, SimpleNamespace(connection=connection))
        self.intent.reservation.refresh_from_db()
        self.job.refresh_from_db()
        before = (self.intent.reservation.status, self.job.status, self.job.result_count)
        AcceptedResult.objects.create(**self.row_values())
        self.intent.reservation.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(
            (self.intent.reservation.status, self.job.status, self.job.result_count), before
        )
        with self.assertRaisesRegex(RuntimeError, "preservation plan"):
            guard(apps, SimpleNamespace(connection=connection))


class PayloadMigrationTests(PayloadFixture, TransactionTestCase):
    def test_legacy_payload_and_fingerprints_survive_reverse_and_reapply(self):
        self.accept()
        row = AcceptedResult.objects.get()
        identity = row.id
        original = (row.acceptance_id, row.record_ref, row.fields, row.field_lineage, row.delete_at)
        fingerprints = list(
            AcceptedFingerprint.objects.order_by("token").values_list("token", flat=True)
        )
        old = [("core", "0019_batch_protocol_selection")]
        new = [("core", "0020_batch_payload_links")]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(old)
            historical = executor.loader.project_state(old).apps.get_model("core", "AcceptedResult")
            saved = historical.objects.get(pk=identity)
            self.assertEqual(
                (
                    saved.acceptance_id,
                    saved.record_ref,
                    saved.fields,
                    saved.field_lineage,
                    saved.delete_at,
                ),
                original,
            )
        finally:
            MigrationExecutor(connection).migrate(new)
        restored = AcceptedResult.objects.get(pk=identity)
        self.assertEqual(
            (
                restored.acceptance_id,
                restored.record_ref,
                restored.fields,
                restored.field_lineage,
                restored.delete_at,
            ),
            original,
        )
        self.assertIsNone(restored.batch_acceptance_id)
        self.assertIsNone(restored.batch_position)
        self.assertEqual(
            list(AcceptedFingerprint.objects.order_by("token").values_list("token", flat=True)),
            fingerprints,
        )

    def test_populated_v3_reverse_refuses_before_schema_or_payload_loss(self):
        row = AcceptedResult.objects.create(**self.row_values())
        with self.assertRaisesRegex(RuntimeError, "preservation plan"):
            MigrationExecutor(connection).migrate([("core", "0019_batch_protocol_selection")])
        saved = AcceptedResult.objects.get(pk=row.pk)
        self.assertEqual(
            (saved.batch_acceptance_id, saved.fields), (row.batch_acceptance_id, row.fields)
        )
        self.assertEqual(saved.batch_position, 1)
        self.assertIn(
            ("core", "0020_batch_payload_links"),
            MigrationExecutor(connection).loader.applied_migrations,
        )


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL batch position race required")
class BatchPayloadRaceTests(PayloadFixture, TransactionTestCase):
    def test_duplicate_batch_position_commits_once(self):
        barrier = Barrier(2)

        def insert(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    AcceptedResult.objects.create(**self.row_values(record_ref=f"race-{index}"))
                return "created"
            except IntegrityError:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(insert, range(2))), ["created", "conflict"])
        self.assertEqual(
            AcceptedResult.objects.filter(batch_acceptance=self.batch_acceptance).count(), 1
        )
