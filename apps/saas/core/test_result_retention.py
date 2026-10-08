import importlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_accepted_results as acceptance_tests
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    Entitlement,
    Membership,
    ResultExport,
    UsageCounter,
    User,
)
from .result_query import results_snapshot
from .result_retention import expire_result_payloads
from .services import create_workspace
from .test_result_exports import ExportFixture


class RetentionFixture(ExportFixture):
    def expire(self, limit=100):
        return expire_result_payloads(self.user, self.workspace.id, limit=limit)

    def due(self):
        AcceptedResult.objects.filter(workspace=self.workspace).update(
            delete_at=timezone.now() - timedelta(seconds=1)
        )


class ResultRetentionTests(RetentionFixture, TestCase):
    def test_due_payload_erasure_retains_dedupe_usage_and_receipt(self):
        receipt = self.export()
        self.due()
        self.assertEqual(self.expire(), {"erased_count": 1, "more_due": False})
        row = AcceptedResult.objects.get()
        self.assertEqual((row.fields, row.field_lineage, row.record_ref), ({}, {}, None))
        self.assertEqual((row.category, row.purpose, row.retention_version), ("", "", ""))
        self.assertIsNotNone(row.erased_at)
        self.assertEqual(row.erased_by_id, self.user.id)
        self.assertEqual(AcceptedFingerprint.objects.count(), 3)
        self.assertTrue(ResultExport.objects.filter(pk=receipt.receipt_id).exists())
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertEqual((counter.leads, counter.exports), (1, 1))
        self.job.refresh_from_db()
        self.assertEqual(self.job.result_count, 1)
        self.assertEqual(
            results_snapshot(self.user, self.workspace.id, self.job.id)["withheld_count"], 1
        )
        with self.assertRaises(PermissionDenied):
            self.export()

    def test_not_due_never_erases_and_repeated_cleanup_is_noop(self):
        self.assertEqual(self.expire()["erased_count"], 0)
        self.due()
        self.expire()
        first = AcceptedResult.objects.get().erased_at
        self.assertEqual(self.expire(), {"erased_count": 0, "more_due": False})
        self.assertEqual(AcceptedResult.objects.get().erased_at, first)

    def test_bounded_multiple_refs_tombstone_without_unique_collisions(self):
        row = AcceptedResult.objects.get()
        row.pk = uuid4()
        row.record_ref = "synthetic-record-2"
        row.save(force_insert=True)
        row.pk = uuid4()
        row.record_ref = "synthetic-record-3"
        row.save(force_insert=True)
        self.due()
        self.assertEqual(self.expire(limit=2), {"erased_count": 2, "more_due": True})
        self.assertEqual(self.expire(limit=2), {"erased_count": 1, "more_due": False})
        self.assertEqual(
            AcceptedResult.objects.filter(record_ref__isnull=True, fields={}).count(), 3
        )

    def test_roles_and_tenant_scope_precede_cleanup(self):
        self.due()
        for role in ["viewer", "member"]:
            Membership.objects.filter(workspace=self.workspace, user=self.user).update(role=role)
            with self.assertRaises(PermissionDenied):
                self.expire()
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="admin")
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        self.assertEqual(expire_result_payloads(self.user, other.id)["erased_count"], 0)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        with self.assertRaises(Http404):
            self.expire()
        self.assertIsNone(AcceptedResult.objects.get().erased_at)

    def test_cleanup_survives_disabled_source_and_inactive_entitlement(self):
        from .models import SourcePolicy

        self.due()
        SourcePolicy.objects.update(enabled=False)
        Entitlement.objects.update(active=False)
        self.assertEqual(self.expire()["erased_count"], 1)

    def test_limit_bounds_and_transaction_rollback(self):
        self.due()
        for value in [0, -1, 101, True, "1"]:
            with self.assertRaises(ValidationError):
                self.expire(limit=value)
        with patch("django.db.models.query.QuerySet.exists", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.expire()
        self.assertIsNone(AcceptedResult.objects.get().erased_at)
        self.assertTrue(AcceptedResult.objects.get().fields)

    def test_tombstone_still_blocks_later_job_duplicate(self):
        self.due()
        self.expire()
        acceptance_tests.AcceptedResultTests.test_duplicate_across_later_job_is_not_new_accepted_use(
            self
        )
        self.assertEqual(AcceptedResult.objects.get().fields, {})

    def test_database_rejects_payload_rehydration_in_erased_state(self):
        self.due()
        self.expire()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcceptedResult.objects.update(fields={"business_name": "Restored"})
        self.assertEqual(AcceptedResult.objects.get().fields, {})

    def test_command_compact_output_and_authorization_failure(self):
        self.due()
        output = io.StringIO()
        call_command(
            "expire_result_payloads",
            workspace=self.workspace.id,
            actor=self.user.id,
            limit=1,
            stdout=output,
        )
        self.assertEqual(output.getvalue(), "Erased 1; more due: False.\n")
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(CommandError):
            call_command(
                "expire_result_payloads",
                workspace=self.workspace.id,
                actor=self.user.id,
                stdout=output,
            )

    def test_erasure_rollback_guard_is_irreversible_only_after_erasure(self):
        migration = importlib.import_module("core.migrations.0015_result_erasure")
        editor = type("Editor", (), {"connection": connection})()
        migration.protect_erasure_rollback(apps, editor)
        self.due()
        self.expire()
        with self.assertRaises(RuntimeError):
            migration.protect_erasure_rollback(apps, editor)


@skipUnless(connection.vendor == "postgresql", "requires real PostgreSQL row locks")
class ResultRetentionConcurrencyTests(RetentionFixture, TransactionTestCase):
    def race(self, export=False):
        barrier = Barrier(2)

        def worker(mode):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.id)
                barrier.wait(timeout=10)
                if mode == "export":
                    from .result_exports import prepare_export

                    prepare_export(user, self.workspace.id, self.job.id, "race", self.selection)
                    return "exported"
                return expire_result_payloads(user, self.workspace.id)["erased_count"]
            except PermissionDenied:
                return "denied"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, ["erase", "export" if export else "erase"]))

    def test_duplicate_expiry_erases_once(self):
        self.due()
        self.assertEqual(sorted(self.race()), [0, 1])
        self.assertEqual(AcceptedFingerprint.objects.count(), 3)

    def test_due_payload_export_and_cleanup_cannot_release_data(self):
        self.due()
        self.assertEqual(self.race(export=True), [1, "denied"])
        self.assertFalse(ResultExport.objects.exists())
        self.assertEqual(AcceptedResult.objects.get().fields, {})
