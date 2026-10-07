from django.test import TestCase

from .models import Membership, SourcePolicy, User
from .services import create_workspace


class SourcePreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="catalog-reader")
        self.workspace = create_workspace(self.user, {"name": "A", "timezone": "UTC"})
        self.page = f"/workspaces/{self.workspace.id}/sources/"
        self.client.force_login(self.user)

    def test_empty_catalog_does_not_seed_policies_or_imply_availability(self):
        response = self.client.get(self.page)
        self.assertContains(response, "No source policies are configured")
        self.assertContains(response, "Provider dispatch is unavailable")
        self.assertContains(response, "Export rights are assessed separately")
        self.assertFalse(SourcePolicy.objects.exists())

    def test_configuration_is_escaped_and_does_not_expose_evidence_or_controls(self):
        SourcePolicy.objects.create(
            code="<script>bad()</script>",
            enabled=True,
            free_collection=True,
            countries=["US", "CA"],
            categories=["<img src=x onerror=bad()>"],
            statuses=["active"],
            fields=["phone"],
            evidence={"collection": "sensitive-evidence-reference"},
            controls={"retention_deletion": "sensitive-control-reference"},
        )
        response = self.client.get(self.page)
        self.assertContains(response, "&lt;script&gt;bad()&lt;/script&gt;")
        self.assertContains(response, "&lt;img src=x onerror=bad()&gt;")
        self.assertNotContains(response, "<script>")
        self.assertNotContains(response, "<img ")
        self.assertNotContains(response, "sensitive-evidence-reference")
        self.assertNotContains(response, "sensitive-control-reference")
        self.assertContains(response, "Enabled in configuration")
        self.assertContains(response, "cost verification is separate")
        self.assertContains(response, "does not establish live availability")

    def test_invalid_metadata_fails_to_unknown_and_read_is_bounded(self):
        SourcePolicy.objects.bulk_create(
            [
                SourcePolicy(
                    code=f"source-{n:03}",
                    countries="US",
                    categories={"not": "a list"},
                    statuses=[123],
                    fields=["x"] * 101,
                )
                for n in range(102)
            ]
        )
        response = self.client.get(self.page)
        self.assertEqual(len(response.context["sources"]), 100)
        self.assertTrue(response.context["truncated"])
        self.assertContains(response, "Additional entries are omitted")
        self.assertNotContains(response, ">source-100</h2>")
        self.assertNotContains(response, ">source-101</h2>")
        for key in ("countries", "categories", "statuses", "fields"):
            self.assertIsNone(response.context["sources"][0][key])

    def test_tenant_revocation_viewer_login_and_method_boundaries(self):
        other = User.objects.create_user(username="other-catalog")
        foreign = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        self.assertEqual(self.client.get(f"/workspaces/{foreign.id}/sources/").status_code, 404)
        Membership.objects.filter(user=self.user, workspace=self.workspace).update(role="viewer")
        self.assertEqual(self.client.get(self.page).status_code, 200)
        for method in (self.client.post, self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(method(self.page).status_code, 405)
        Membership.objects.filter(user=self.user, workspace=self.workspace).delete()
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 302)


class SourceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="catalog-api")
        self.workspace = create_workspace(self.user, {"name": "API", "timezone": "UTC"})
        self.page = f"/api/v1/workspaces/{self.workspace.id}/sources/"
        self.client.force_login(self.user)

    def test_empty_private_catalog_has_no_activation_or_evidence(self):
        response = self.client.get(self.page)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], [])
        self.assertFalse(response.json()["truncated"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(SourcePolicy.objects.exists())
        SourcePolicy.objects.create(
            code="synthetic",
            countries=["US"],
            evidence={"collection": "private-evidence"},
            controls={"rate_limit": "private-control"},
        )
        entry = self.client.get(self.page).json()["sources"][0]
        self.assertEqual(entry["countries"], ["US"])
        self.assertFalse(entry["metadata_limited"])
        self.assertNotIn("evidence", entry)
        self.assertNotIn("controls", entry)

    def test_huge_valid_metadata_is_explicitly_unavailable_with_bounded_wire_response(self):
        import json

        SourcePolicy.objects.bulk_create(
            [
                SourcePolicy(
                    code=f"source-{i:03}",
                    countries=["US"],
                    categories=["界" * 120] * 100,
                    fields=["phone"],
                )
                for i in range(101)
            ]
        )
        data = self.client.get(self.page).json()
        self.assertEqual(len(data["sources"]), 100)
        self.assertTrue(data["truncated"])
        self.assertLess(len(json.dumps(data, ensure_ascii=True).encode()), 131072)
        for entry in data["sources"]:
            self.assertTrue(entry["metadata_limited"])
            for key in ["countries", "categories", "statuses", "fields"]:
                self.assertIsNone(entry[key])

    def test_viewer_can_read_but_foreign_revoked_anonymous_and_write_are_denied(self):
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(self.page).status_code, 200)
        other = User.objects.create_user(username="foreign-source-api")
        foreign = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        self.assertEqual(
            self.client.get(f"/api/v1/workspaces/{foreign.id}/sources/").status_code, 404
        )
        self.assertEqual(
            self.client.post(self.page, "{}", content_type="application/json").status_code, 405
        )
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.page).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 403)
