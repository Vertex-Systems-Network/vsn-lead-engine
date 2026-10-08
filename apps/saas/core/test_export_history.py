from datetime import timedelta
from unittest.mock import patch

from django.core import signing
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .export_history import SALT, receipt_snapshot
from .models import Entitlement, Membership, ResultExport, SourcePolicy, UsageCounter, User
from .result_exports import prepare_export
from .services import create_draft
from .test_result_exports import ExportFixture


class ExportHistoryTests(ExportFixture, TestCase):
    def setUp(self):
        super().setUp()
        Entitlement.objects.filter(workspace=self.workspace).update(export_limit=30)
        self.history_url = self.url.replace("exports/", "export-receipts/")
        self.client.force_login(self.user)

    def test_private_readonly_metadata_is_not_download_authority_or_delivery(self):
        prepared = self.export()
        response = self.client.get(self.history_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertEqual(data["scope"], "job")
        self.assertEqual(data["receipts"][0]["id"], str(prepared.receipt_id))
        self.assertEqual(
            (data["receipts"][0]["record_count"], data["receipts"][0]["export_units"]), (1, 1)
        )
        for secret in [
            "phone",
            "50123",
            "business_name",
            "request_hash",
            "content_digest",
            "test-export",
            "created_by",
            "record_ref",
        ]:
            self.assertNotIn(secret, response.content.decode())
        SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with patch(
            "core.export_history.timezone.now",
            return_value=prepared.delete_at + timedelta(seconds=1),
        ):
            history = receipt_snapshot(self.user, self.workspace.id, self.job.id)
        self.assertTrue(history["receipts"][0]["deadline_passed"])
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)
        self.assertEqual(ResultExport.objects.count(), 1)

    def test_members_see_only_own_preparations_and_viewers_are_denied(self):
        own = self.export()
        other = User.objects.create_user(username="other-preparer")
        Membership.objects.create(workspace=self.workspace, user=other, role="owner")
        prepare_export(other, self.workspace.id, self.job.id, "other-file", self.selection)
        self.assertEqual(len(self.client.get(self.history_url).json()["receipts"]), 2)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="member")
        data = self.client.get(self.history_url).json()
        self.assertEqual(data["scope"], "own")
        self.assertEqual([r["id"] for r in data["receipts"]], [str(own.receipt_id)])
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(self.history_url).status_code, 403)
        self.assertFalse(
            self.client.get(self.url.replace("exports/", "results/")).json()["can_review_receipts"]
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.history_url + "?after=bad").status_code, 404)

    def test_signed_pages_are_bounded_stable_and_actor_job_scope_bound(self):
        for i in range(26):
            self.export(key=f"prepared-{i}")
        ResultExport.objects.update(created_at=timezone.now())
        first = self.client.get(self.history_url).json()
        self.assertEqual(len(first["receipts"]), 25)
        second = self.client.get(self.history_url, {"after": first["next_cursor"]}).json()
        self.assertEqual(len(second["receipts"]), 1)
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(len({r["id"] for r in first["receipts"] + second["receipts"]}), 26)
        other = User.objects.create_user(username="other-reader")
        Membership.objects.create(workspace=self.workspace, user=other, role="admin")
        with self.assertRaises(ValidationError):
            receipt_snapshot(other, self.workspace.id, self.job.id, first["next_cursor"])
        job, _ = create_draft(self.user, self.workspace.id, self.job.search, "other-job")
        with self.assertRaises(ValidationError):
            receipt_snapshot(self.user, self.workspace.id, job.id, first["next_cursor"])
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="member")
        with self.assertRaises(ValidationError):
            receipt_snapshot(self.user, self.workspace.id, self.job.id, first["next_cursor"])
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 26)

    def test_bad_expired_and_naive_continuations_do_not_write(self):
        payload = {
            "binding": [str(self.user.id), str(self.workspace.id), str(self.job.id), "job"],
            "created": "2026-10-08T00:00:00",
            "id": str(self.job.id),
        }
        naive = signing.dumps(payload, salt=SALT)
        payload["created"] = timezone.now().isoformat()
        with patch(
            "django.core.signing.time.time", return_value=timezone.now().timestamp() - 86401
        ):
            expired = signing.dumps(payload, salt=SALT)
        for token in ["", "x" * 1025, naive, expired, expired + "x"]:
            self.assertEqual(self.client.get(self.history_url, {"after": token}).status_code, 400)
        self.assertFalse(ResultExport.objects.exists())
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 0)

    def test_foreign_paths_unknown_queries_and_mutation_methods_are_denied(self):
        from .services import create_workspace

        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        response = self.client.get(self.history_url.replace(str(self.workspace.id), str(other.id)))
        self.assertEqual(response.status_code, 404)
        for query in ["all=1", "page=1", "after=a&after=b"]:
            self.assertEqual(self.client.get(self.history_url + "?" + query).status_code, 400)
        for method in ["post", "put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(self.history_url, {}).status_code, 405)
        self.assertFalse(ResultExport.objects.exists())

    def test_unsettled_receipt_is_not_presented_as_charged_preparation(self):
        self.export()
        receipt = ResultExport.objects.get()
        receipt.reservation.status = "reserved"
        receipt.reservation.save()
        self.assertEqual(self.client.get(self.history_url).json()["receipts"], [])
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)
