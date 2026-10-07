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
