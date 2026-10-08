import csv
import importlib
import io
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .jobs import enqueue_job
from .models import (
    AcceptedResult,
    Entitlement,
    Membership,
    ResultExport,
    SourcePolicy,
    UsageCounter,
    UsageReservation,
    User,
)
from .result_exports import csv_cell, prepare_export
from .result_query import results_snapshot
from .services import IdempotencyConflict, create_workspace
from .test_accepted_results import AcceptanceFixture

EXPORT_RIGHTS = {
    "version": 1,
    "allowed": True,
    "fields": ["business_name", "phone"],
    "purpose": "synthetic-test-only",
    "retention_version": "synthetic-v1",
    "attribution": "Synthetic test source; no live rights",
}


class ExportFixture(AcceptanceFixture):
    def setUp(self):
        def enqueue_with_rights(*args, **kwargs):
            policy = SourcePolicy.objects.get(pk="fixture")
            policy.controls["export_contract"] = deepcopy(EXPORT_RIGHTS)
            policy.save()
            return enqueue_job(*args, **kwargs)

        with patch("core.test_result_evidence.enqueue_job", enqueue_with_rights):
            super().setUp()
        self.accept()
        Entitlement.objects.filter(workspace=self.workspace).update(export_limit=1)
        self.selection = {
            "result_ids": [str(AcceptedResult.objects.get().id)],
            "fields": ["phone", "business_name"],
        }
        self.url = f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/exports/"

    def export(self, key="test-export", data=None):
        return prepare_export(
            self.user, self.workspace.id, self.job.id, key, self.selection if data is None else data
        )


class ResultExportTests(ExportFixture, TestCase):
    def test_once_only_bounded_csv_accounting_and_replay(self):
        first = self.export()
        replay = self.export(data={**self.selection, "fields": ["business_name", "phone"]})
        self.assertTrue(first.created)
        self.assertFalse(replay.created)
        self.assertEqual(first.receipt_id, replay.receipt_id)
        self.assertEqual(first.csv_bytes, replay.csv_bytes)
        rows = list(csv.reader(io.StringIO(first.csv_bytes.decode())))
        self.assertEqual(rows[0][:2], ["business_name", "phone"])
        self.assertTrue(rows[1][1].startswith("'+1"))
        self.assertIn(EXPORT_RIGHTS["attribution"], rows[1])
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)
        self.assertEqual(ResultExport.objects.count(), 1)
        self.assertEqual(UsageReservation.objects.filter(exports=1, status="settled").count(), 1)
        for value in ["record_ref", "signature", "body_hash", "synthetic-record-1"]:
            self.assertNotIn(value, first.csv_bytes.decode())

    def test_conflicting_key_and_caps_never_recharge(self):
        self.export()
        with self.assertRaises(IdempotencyConflict):
            self.export(data={**self.selection, "fields": ["phone"]})
        with self.assertRaises(ValidationError):
            self.export(key="another-export")
        self.assertEqual(ResultExport.objects.count(), 1)

    def test_pending_reservations_are_included_in_cap(self):
        UsageReservation.objects.create(
            workspace=self.workspace, key="pending-other", request_hash="0" * 64, exports=1
        )
        with self.assertRaises(ValidationError):
            self.export()
        self.assertFalse(ResultExport.objects.exists())

    def test_current_roles_and_creator_bound_replay(self):
        self.export()
        for role in ["member", "admin", "owner"]:
            Membership.objects.filter(workspace=self.workspace, user=self.user).update(role=role)
            self.assertFalse(self.export().created)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            self.export()
        other = User.objects.create_user(username="export-other")
        Membership.objects.create(workspace=self.workspace, user=other, role="member")
        with self.assertRaises(IdempotencyConflict):
            prepare_export(other, self.workspace.id, self.job.id, "test-export", self.selection)

    def test_expiry_and_current_source_rights_deny_replay(self):
        self.export()
        policy = SourcePolicy.objects.get(pk="fixture")
        for changes in [{"enabled": False}, {"version": 2}, {"controls": {}}]:
            originals = {k: deepcopy(getattr(policy, k)) for k in changes}
            SourcePolicy.objects.filter(pk=policy.pk).update(**changes)
            with self.assertRaises(PermissionDenied):
                self.export()
            SourcePolicy.objects.filter(pk=policy.pk).update(**originals)
        AcceptedResult.objects.update(delete_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(PermissionDenied):
            self.export()
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)

    def test_payload_change_cannot_change_replay_csv(self):
        self.export()
        row = AcceptedResult.objects.get()
        row.fields["business_name"] = "Changed example"
        row.save()
        with self.assertRaises(IdempotencyConflict):
            self.export()

    def test_absent_export_grant_never_follows_from_display_rights(self):
        snapshot = results_snapshot(self.user, self.workspace.id, self.job.id)
        policy = SourcePolicy.objects.get(pk="fixture")
        policy.controls.pop("export_contract")
        policy.save()
        with patch("core.result_exports.results_snapshot", return_value=snapshot):
            with self.assertRaises(PermissionDenied):
                self.export()
        self.assertFalse(ResultExport.objects.exists())

    def test_explicit_export_contract_schema_and_entitlement_fail_closed(self):
        snapshot = results_snapshot(self.user, self.workspace.id, self.job.id)
        policy = SourcePolicy.objects.get(pk="fixture")
        for value in [
            None,
            {},
            {**EXPORT_RIGHTS, "allowed": 1},
            {**EXPORT_RIGHTS, "version": True},
            {**EXPORT_RIGHTS, "fields": ["private"]},
            {**EXPORT_RIGHTS, "purpose": "other"},
            {**EXPORT_RIGHTS, "retention_version": "other"},
            {**EXPORT_RIGHTS, "attribution": "\nformula"},
            {**EXPORT_RIGHTS, "extra": True},
        ]:
            policy.controls["export_contract"] = value
            policy.save()
            with patch("core.result_exports.results_snapshot", return_value=snapshot):
                with self.assertRaises(PermissionDenied):
                    self.export()
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.export()
        self.assertFalse(ResultExport.objects.exists())

    def test_bounded_selection_and_unavailable_records_fail_closed(self):
        invalid = [
            None,
            {},
            {**self.selection, "all": True},
            {**self.selection, "fields": ["private"]},
            {**self.selection, "fields": ["phone"] * 2},
            {**self.selection, "result_ids": ["x"]},
            {**self.selection, "result_ids": self.selection["result_ids"] * 26},
        ]
        for value in invalid:
            with self.assertRaises(ValidationError):
                prepare_export(self.user, self.workspace.id, self.job.id, "test", value)
        for value in [
            {**self.selection, "result_ids": [str(uuid4())]},
            {**self.selection, "fields": ["website"]},
        ]:
            with self.assertRaises(PermissionDenied):
                self.export(data=value)
        self.assertFalse(ResultExport.objects.exists())

    def test_atomic_rollback_on_receipt_failure(self):
        with patch("core.result_exports.ResultExport.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.export()
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 0)
        self.assertFalse(UsageReservation.objects.filter(exports=1).exists())

    def test_csv_structure_and_formula_prefixes(self):
        for value in ["=SUM(1,2)", "+15551234567", "-1", " @cmd", "\u2003=1"]:
            self.assertEqual(csv_cell(value), "'" + value)
        self.assertEqual(csv_cell('Acme, "quoted"'), 'Acme, "quoted"')
        row = AcceptedResult.objects.get()
        row.fields["business_name"] = ' =SUM(1,2), "example"'
        row.save()
        rows = list(csv.reader(io.StringIO(self.export().csv_bytes.decode())))
        self.assertEqual(rows[1][0], "'" + row.fields["business_name"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]), len(rows[1]))

    def test_http_post_is_csrf_protected_private_and_get_is_readonly(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.get(self.url).status_code, 405)
        self.assertEqual(
            client.post(
                self.url,
                self.selection,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="http",
            ).status_code,
            403,
        )
        client.get("/accounts/check-session/")
        response = client.post(
            self.url,
            self.selection,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="http",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        foreign = create_workspace(self.user, {"name": "Foreign", "timezone": "UTC"})
        self.assertEqual(
            client.post(
                f"/api/v1/workspaces/{foreign.id}/jobs/{self.job.id}/exports/",
                self.selection,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="foreign",
                HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
            ).status_code,
            403,
        )

    def test_populated_export_rollback_guard(self):
        migration = importlib.import_module("core.migrations.0014_resultexport")
        editor = type("Editor", (), {"connection": connection})()
        migration.protect_export_rollback(apps, editor)
        self.export()
        with self.assertRaises(RuntimeError):
            migration.protect_export_rollback(apps, editor)


@skipUnless(connection.vendor == "postgresql", "requires real PostgreSQL row locks")
class ResultExportConcurrencyTests(ExportFixture, TransactionTestCase):
    def race(self, keys):
        barrier = Barrier(2)

        def worker(key):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                result = prepare_export(user, self.workspace.id, self.job.id, key, self.selection)
                return (str(result.receipt_id), result.created)
            except ValidationError:
                return "cap"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, keys))

    def test_duplicate_export_commits_once(self):
        outcomes = self.race(["same", "same"])
        self.assertEqual(outcomes[0][0], outcomes[1][0])
        self.assertEqual(sum(x[1] for x in outcomes), 1)
        self.assertEqual(ResultExport.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)

    def test_competing_exports_cannot_exceed_cap(self):
        outcomes = self.race(["first", "second"])
        self.assertEqual(outcomes.count("cap"), 1)
        self.assertEqual(ResultExport.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)
