"""Synthetic signed acceptance; no live sources, registry or commercial rights."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .export_forms import confirmed_selection, export_context
from .models import (
    AcceptedResult,
    Entitlement,
    Membership,
    ResultExport,
    SourcePolicy,
    UsageCounter,
)
from .result_exports import prepare_export
from .result_retention import expire_result_payloads
from .serializers import SearchSerializer
from .services import create_draft, create_workspace
from .test_accepted_results import AcceptanceFixture
from .test_jobs import fixture
from .test_result_exports import EXPORT_RIGHTS


class MetadataAcceptanceFixture(AcceptanceFixture):
    def setUp(self):
        def metadata_fixture():
            user, workspace, original = fixture()
            policy = SourcePolicy.objects.get(pk="fixture")
            policy.countries = ["US", "CA"]
            policy.categories = ["software", "z-second"]
            policy.controls["export_contract"] = deepcopy(EXPORT_RIGHTS)
            policy.save()
            search = SearchSerializer(
                data={
                    **original.search,
                    "countries": ["US", "CA"],
                    "categories": ["software", "z-second"],
                }
            )
            search.is_valid(raise_exception=True)
            job, _ = create_draft(user, workspace.id, search.validated_data, "metadata-fixture")
            return user, workspace, job

        with patch("core.test_result_evidence.fixture", metadata_fixture):
            super().setUp()
        self.acceptance_data["records"].append(
            {
                "record_ref": "synthetic-record-2",
                "tokens": ["n:" + "4" * 24, "l:" + "5" * 24, "s:" + "6" * 24],
            }
        )
        self.accept()
        Entitlement.objects.filter(workspace=self.workspace).update(export_limit=3)
        self.url = f"/api/v1/workspaces/{self.workspace.id}/jobs/{self.job.id}/results/"

    def candidate_signed(self, data=None):
        if len(self.data["records"]) == 1:
            row = deepcopy(self.data["records"][0])
            row.update(record_ref="synthetic-record-2", country="CA", category="z-second")
            row["fields"] = {"business_name": "Second synthetic", "phone": "+12025550124"}
            row["field_lineage"] = dict.fromkeys(row["fields"], row["record_ref"])
            self.data["records"].append(row)
        return super().candidate_signed(data)


class ResultMetadataFilterTests(MetadataAcceptanceFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_compound_filters_use_saved_metadata_and_do_not_change_usage(self):
        data = self.client.get(self.url + "?country=CA&category=1&source=0").json()
        self.assertEqual(data["category_options"], ["software", "z-second"])
        self.assertEqual(data["source_options"], ["fixture"])
        self.assertEqual(
            (len(data["results"]), data["filtered_count"], data["withheld_count"]), (1, 1, 0)
        )
        self.assertEqual(data["results"][0]["fields"]["phone"], "+12025550124")
        empty = self.client.get(self.url + "?country=US&category=1&source=0").json()
        self.assertEqual(
            (empty["results"], empty["filtered_count"], empty["withheld_count"]), ([], 2, 0)
        )
        self.assertFalse(empty["can_review_export"])
        self.assertEqual(len(self.client.get(self.url + "?category=&source=").json()["results"]), 2)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 0)
        self.assertFalse(ResultExport.objects.exists())

    def test_unknown_repeated_noncanonical_and_out_of_scope_filters_fail_closed(self):
        for query in [
            "category=12",
            "category=-1",
            "category=01",
            "category=2",
            "category=software",
            "source=1",
            "source=fixture",
            "source=0&source=0",
            "category=0&category=1",
            "extra=1",
        ]:
            self.assertEqual(self.client.get(self.url + "?" + query).status_code, 400)
        self.assertFalse(ResultExport.objects.exists())

    def test_rights_and_expiry_withheld_counts_are_not_filter_counts(self):
        row = AcceptedResult.objects.get(job=self.job, category="software")
        AcceptedResult.objects.filter(pk=row.pk).update(
            delete_at=timezone.now() - timedelta(seconds=1)
        )
        filtered = self.client.get(self.url + "?category=0&source=0").json()
        self.assertEqual(
            (filtered["results"], filtered["withheld_count"], filtered["filtered_count"]),
            ([], 1, 1),
        )
        SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
        withheld = self.client.get(self.url + "?category=1&source=0").json()
        self.assertEqual(
            (withheld["results"], withheld["withheld_count"], withheld["filtered_count"]),
            ([], 2, 0),
        )
        self.assertEqual(withheld["category_options"], ["software", "z-second"])

    def test_filtered_confirmation_cannot_add_other_authorized_rows_and_rechecks_erasure(self):
        context = export_context(
            self.user, self.workspace.id, self.job.id, category="1", source="0"
        )
        selected = context["records"][0]["id"]
        other = str(AcceptedResult.objects.get(job=self.job, category="software").id)
        with self.assertRaises(ValidationError):
            confirmed_selection(
                self.user,
                self.workspace.id,
                self.job.id,
                context["confirmation"],
                ["phone"],
                [other],
            )
        key, data = confirmed_selection(
            self.user,
            self.workspace.id,
            self.job.id,
            context["confirmation"],
            ["phone"],
            [selected],
        )
        first = prepare_export(self.user, self.workspace.id, self.job.id, key, data)
        self.assertEqual(first.record_count, 1)
        self.assertIn(b"50124", first.csv_bytes)
        self.assertNotIn(b"50123", first.csv_bytes)
        self.assertEqual(
            prepare_export(self.user, self.workspace.id, self.job.id, key, data).receipt_id,
            first.receipt_id,
        )
        AcceptedResult.objects.filter(pk=selected).update(
            delete_at=timezone.now() - timedelta(seconds=1)
        )
        expire_result_payloads(self.user, self.workspace.id)
        with self.assertRaises(PermissionDenied):
            prepare_export(self.user, self.workspace.id, self.job.id, key, data)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).exports, 1)
        with self.assertRaises(PermissionDenied):
            export_context(self.user, self.workspace.id, self.job.id, category="1")

    def test_current_membership_precedes_filter_validation_and_private_metadata(self):
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertEqual(self.client.get(self.url + "?category=1").status_code, 200)
        with self.assertRaises(PermissionDenied):
            export_context(self.user, self.workspace.id, self.job.id, category="1")
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        foreign = self.url.replace(str(self.workspace.id), str(other.id))
        response = self.client.get(foreign + "?category=1")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("z-second", response.content.decode())
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.client.get(self.url + "?category=12").status_code, 404)

    def test_malformed_or_oversized_saved_metadata_does_not_leak_rows(self):
        for categories in [
            ["x"] * 13,
            ["software", "software"],
            ["private\nvalue"],
            {"private": "value"},
        ]:
            from .models import Job

            Job.objects.filter(pk=self.job.pk).update(
                search={**self.job.search, "categories": categories}
            )
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("50123", response.content.decode())
