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
        values = {"confirmation": token, "fields": ["phone"], "csrfmiddlewaretoken": self.csrf}
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
                confirmed_selection(self.user, self.workspace.id, self.job.id, token, fields)
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(ValidationError):
            confirmed_selection(self.user, other.id, self.job.id, token, ["phone"])
        data = signing.loads(token, salt=SALT)
        for change in [
            {"user": "other"},
            {"job": "other"},
            {"expires": (timezone.now() - timedelta(seconds=1)).isoformat()},
        ]:
            invalid = signing.dumps({**data, **change}, salt=SALT)
            with self.assertRaises(ValidationError):
                confirmed_selection(self.user, self.workspace.id, self.job.id, invalid, ["phone"])
        with self.assertRaises(ValidationError):
            confirmed_selection(self.user, self.workspace.id, self.job.id, token + "x", ["phone"])

    def test_revocation_viewer_expiry_and_erasure_remain_authoritative(self):
        token = export_context(self.user, self.workspace.id, self.job.id)["confirmation"]
        values = {"confirmation": token, "fields": ["phone"], "csrfmiddlewaretoken": self.csrf}
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
        values = {"confirmation": token, "fields": ["phone"], "csrfmiddlewaretoken": self.csrf}
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
