from datetime import timedelta

from django.core import signing
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .export_forms import SALT, confirmed_selection, export_context
from .models import Membership, ResultExport, UsageCounter
from .result_retention import expire_result_payloads
from .services import create_workspace
from .test_result_exports import ExportFixture


class ExportFormTests(ExportFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.context_url = self.url.replace("exports/", "export-form/")
        self.submit_url = self.url.replace("/api/v1", "").replace("exports/", "export/")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.client.get("/accounts/check-session/")
        self.csrf = self.client.cookies["csrftoken"].value

    def test_private_bounded_preview_is_readonly_and_explains_omissions(self):
        response = self.client.get(self.context_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertEqual((data["record_count"], data["withheld_count"]), (1, 0))
        self.assertEqual(data["fields"], ["business_name", "phone"])
        self.assertIn("website", data["omitted_fields"])
        self.assertEqual(len(data["csrf_token"]), 64)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 0)
        self.assertFalse(ResultExport.objects.exists())
        self.assertNotIn("synthetic-record-1", str(data))

    def test_confirmation_csv_and_once_only_replay(self):
        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        values = {
            "confirmation": token,
            "fields": ["phone"],
            "result_ids": self.selection["result_ids"],
            "csrfmiddlewaretoken": self.csrf,
        }
        first = self.client.post(self.submit_url, values)
        self.assertEqual(first.status_code, 200)
        self.assertIn(b"'+1", first.content)
        replay = self.client.post(self.submit_url, values)
        self.assertEqual(first.content, replay.content)
        self.assertEqual(first["X-Export-Receipt"], replay["X-Export-Receipt"])
        changed = self.client.post(self.submit_url, {**values, "fields": ["business_name"]})
        self.assertEqual(changed.status_code, 409)
        self.assertContains(changed, "Export needs review", status_code=409)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)

    def test_token_actor_tenant_job_expiry_and_field_scope(self):
        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        for fields in [[], ["website"], ["phone", "phone"]]:
            with self.assertRaises(ValidationError):
                confirmed_selection(
                    self.user,
                    self.workspace.id,
                    self.job.id,
                    token,
                    fields,
                    self.selection["result_ids"],
                )
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(ValidationError):
            confirmed_selection(
                self.user, other.id, self.job.id, token, ["phone"], self.selection["result_ids"]
            )
        data = signing.loads(token, salt=SALT)
        for change in [
            {"user": "other"},
            {"job": "other"},
            {"expires": (timezone.now() - timedelta(seconds=1)).isoformat()},
        ]:
            invalid = signing.dumps({**data, **change}, salt=SALT)
            with self.assertRaises(ValidationError):
                confirmed_selection(
                    self.user,
                    self.workspace.id,
                    self.job.id,
                    invalid,
                    ["phone"],
                    self.selection["result_ids"],
                )
        with self.assertRaises(ValidationError):
            confirmed_selection(
                self.user,
                self.workspace.id,
                self.job.id,
                token + "x",
                ["phone"],
                self.selection["result_ids"],
            )

    def test_revocation_viewer_expiry_and_erasure_remain_authoritative(self):
        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        values = {
            "confirmation": token,
            "fields": ["phone"],
            "result_ids": self.selection["result_ids"],
            "csrfmiddlewaretoken": self.csrf,
        }
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(self.context_url).status_code, 403)
        self.assertEqual(self.client.post(self.submit_url, values).status_code, 403)
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="owner")
        from .models import AcceptedResult

        AcceptedResult.objects.update(delete_at=timezone.now() - timedelta(seconds=1))
        expire_result_payloads(self.user, self.workspace.id)
        self.assertEqual(self.client.post(self.submit_url, values).status_code, 403)
        self.assertFalse(ResultExport.objects.exists())

    def test_csrf_query_and_unknown_repeated_inputs_do_not_prepare(self):
        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        values = {
            "confirmation": token,
            "fields": ["phone"],
            "result_ids": self.selection["result_ids"],
            "csrfmiddlewaretoken": self.csrf,
        }
        self.assertEqual(
            self.client.post(
                self.submit_url, {"confirmation": token, "fields": ["phone"]}
            ).status_code,
            403,
        )
        for data in [{**values, "confirmation": [token, token]}, {**values, "extra": "x"}]:
            self.assertEqual(self.client.post(self.submit_url, data).status_code, 400)
        self.assertEqual(self.client.get(self.submit_url).status_code, 405)
        self.assertEqual(self.client.get(self.context_url + "?all=1").status_code, 400)
        self.assertFalse(ResultExport.objects.exists())

    def test_missing_browser_cookie_and_exhausted_budget_do_not_mint_preview(self):
        self.client.cookies.pop("csrftoken")
        self.assertEqual(self.client.get(self.context_url).status_code, 403)
        self.export()
        with self.assertRaises(PermissionDenied):
            export_context(self.user, self.workspace.id, self.job.id)

    def test_empty_duplicate_foreign_and_oversized_selections_do_not_prepare(self):
        from uuid import uuid4

        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        for ids in [
            [],
            self.selection["result_ids"] * 2,
            [str(uuid4())],
            [str(uuid4()) for _ in range(26)],
        ]:
            response = self.client.post(
                self.submit_url,
                {
                    "confirmation": token,
                    "fields": ["phone"],
                    "result_ids": ids,
                    "csrfmiddlewaretoken": self.csrf,
                },
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(ResultExport.objects.exists())
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 0)

    def test_previous_all_row_confirmation_requires_new_preview(self):
        context = export_context(self.user, self.workspace.id, self.job.id)
        data = signing.loads(context["confirmation"], salt=SALT)
        old = signing.dumps(data, salt="saas.export-confirmation.v1")
        with self.assertRaises(ValidationError):
            confirmed_selection(
                self.user,
                self.workspace.id,
                self.job.id,
                old,
                ["phone"],
                self.selection["result_ids"],
            )


class MultiRowSelectionTests(TestCase):
    def setUp(self):
        from copy import deepcopy
        from unittest.mock import patch

        from .jobs import enqueue_job
        from .models import Entitlement, SourcePolicy
        from .test_accepted_results import AcceptanceFixture
        from .test_result_exports import EXPORT_RIGHTS

        class MultiRowFixture(AcceptanceFixture):
            def addCleanup(inner, callback):
                self.addCleanup(callback)

            def candidate_signed(inner, data=None):
                if len(inner.data["records"]) == 1:
                    row = deepcopy(inner.data["records"][0])
                    row["record_ref"] = "synthetic-record-2"
                    row["fields"] = {"business_name": "Second synthetic", "phone": "+12025550124"}
                    row["field_lineage"] = dict.fromkeys(row["fields"], row["record_ref"])
                    inner.data["records"].append(row)
                return super().candidate_signed(data)

        def enqueue_with_rights(*args, **kwargs):
            policy = SourcePolicy.objects.get(pk="fixture")
            policy.controls["export_contract"] = deepcopy(EXPORT_RIGHTS)
            policy.save()
            return enqueue_job(*args, **kwargs)

        self.fixture = MultiRowFixture()
        with patch("core.test_result_evidence.enqueue_job", enqueue_with_rights):
            self.fixture.setUp()
        self.fixture.acceptance_data["records"].append(
            {
                "record_ref": "synthetic-record-2",
                "tokens": ["n:" + "4" * 24, "l:" + "5" * 24, "s:" + "6" * 24],
            }
        )
        self.fixture.accept()
        Entitlement.objects.filter(workspace=self.fixture.workspace).update(export_limit=3)

    def test_subset_only_csv_replay_and_changed_selection_conflict(self):
        from .result_exports import prepare_export
        from .services import IdempotencyConflict

        f = self.fixture
        preview = export_context(f.user, f.workspace.id, f.job.id)
        self.assertEqual(preview["record_count"], 2)
        self.assertEqual(len(preview["records"]), 2)
        chosen = next(
            r["id"] for r in preview["records"] if r["business_name"] == "Second synthetic"
        )
        key, data = confirmed_selection(
            f.user, f.workspace.id, f.job.id, preview["confirmation"], ["phone"], [chosen]
        )
        result = prepare_export(f.user, f.workspace.id, f.job.id, key, data)
        self.assertEqual(result.record_count, 1)
        self.assertIn(b"50124", result.csv_bytes)
        self.assertNotIn(b"50123", result.csv_bytes)
        self.assertEqual(
            prepare_export(f.user, f.workspace.id, f.job.id, key, data).receipt_id,
            result.receipt_id,
        )
        all_ids = [r["id"] for r in preview["records"]]
        _, changed = confirmed_selection(
            f.user, f.workspace.id, f.job.id, preview["confirmation"], ["phone"], all_ids
        )
        with self.assertRaises(IdempotencyConflict):
            prepare_export(f.user, f.workspace.id, f.job.id, key, changed)
        self.assertEqual(UsageCounter.objects.get(workspace=f.workspace).exports, 1)

    def test_unselected_erasure_does_not_expand_or_invalidate_current_subset(self):
        from .models import AcceptedResult
        from .result_exports import prepare_export

        f = self.fixture
        preview = export_context(f.user, f.workspace.id, f.job.id)
        selected, unselected = preview["records"]
        AcceptedResult.objects.filter(pk=unselected["id"]).update(
            delete_at=timezone.now() - timedelta(seconds=1)
        )
        expire_result_payloads(f.user, f.workspace.id)
        key, data = confirmed_selection(
            f.user, f.workspace.id, f.job.id, preview["confirmation"], ["phone"], [selected["id"]]
        )
        self.assertEqual(
            prepare_export(f.user, f.workspace.id, f.job.id, key, data).record_count, 1
        )

    def test_country_preview_is_bounded_readonly_and_cannot_mint_empty_scope(self):
        f = self.fixture
        context = export_context(f.user, f.workspace.id, f.job.id, "US")
        self.assertEqual(
            (context["record_count"], context["filtered_count"], context["country"]), (2, 0, "US")
        )
        with self.assertRaises(PermissionDenied):
            export_context(f.user, f.workspace.id, f.job.id, "CA")
        self.assertFalse(ResultExport.objects.exists())
        self.assertEqual(UsageCounter.objects.get(workspace=f.workspace).exports, 0)
