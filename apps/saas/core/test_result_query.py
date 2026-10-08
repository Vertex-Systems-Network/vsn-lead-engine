from copy import deepcopy
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from . import test_accepted_results as fixtures
from .models import AcceptedResult, Membership, SourcePolicy
from .services import create_workspace


class ResultQueryTests(fixtures.AcceptanceFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.accept()
        self.client.force_login(self.user)
        self.url = f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/results/"

    def test_bounded_redacted_authorized_payload_and_no_store(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        data = response.json()
        self.assertEqual(
            (data["workspace_id"], data["job_id"], data["withheld_count"]),
            (str(self.workspace.id), str(self.job.id), 0),
        )
        self.assertEqual(len(data["results"]), 1)
        row = data["results"][0]
        self.assertEqual(row["fields"], self.data["records"][0]["fields"])
        self.assertEqual(row["source_code"], "fixture")
        self.assertEqual(row["provenance_fields"], ["business_name", "phone"])
        for secret in ["record_ref", "body_hash", "key_id", "tokens", "signature", "namespace"]:
            self.assertNotIn(secret, str(data))

    def test_viewer_reads_revoked_and_foreign_paths_are_denied(self):
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        self.assertEqual(
            self.client.get(
                f"/api/v1/workspaces/{other.id}/jobs/{self.job.id}/results/"
            ).status_code,
            404,
        )
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_expired_results_are_withheld_without_accounting_or_cleanup(self):
        AcceptedResult.objects.filter(job=self.job).update(
            delete_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.client.get(self.url).json()["results"], [])
        self.assertEqual(self.client.get(self.url).json()["withheld_count"], 1)
        self.assertEqual(AcceptedResult.objects.count(), 1)
        self.job.refresh_from_db()
        self.assertEqual(self.job.result_count, 1)

    def test_live_source_disable_and_fingerprint_drift_withhold_payload(self):
        policy = SourcePolicy.objects.get(pk="fixture")
        for changes in [{"enabled": False}, {"version": 2}, {"controls": {}}, {"evidence": {}}]:
            originals = {key: deepcopy(getattr(policy, key)) for key in changes}
            SourcePolicy.objects.filter(pk="fixture").update(**changes)
            self.assertEqual(self.client.get(self.url).json()["results"], [])
            SourcePolicy.objects.filter(pk="fixture").update(**originals)
        self.assertEqual(len(self.client.get(self.url).json()["results"]), 1)

    def test_malformed_unknown_oversized_payloads_are_withheld(self):
        saved = AcceptedResult.objects.get()
        for value in [
            [],
            {"business_name": "Test"},
            {**saved.fields, "private_field": "hidden"},
            {**saved.fields, "business_name": "漢" * 2000},
        ]:
            AcceptedResult.objects.filter(pk=saved.pk).update(fields=value)
            data = self.client.get(self.url).json()
            self.assertEqual(data["results"], [])
            self.assertEqual(data["withheld_count"], 1)

    def test_query_and_mutation_methods_are_unavailable(self):
        for query in ["after=x", "country=US", "page=10000", "source=other"]:
            self.assertEqual(self.client.get(self.url + "?" + query).status_code, 400)
        for method in ["post", "put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(self.url, {}).status_code, 405)
        self.assertEqual(AcceptedResult.objects.count(), 1)
