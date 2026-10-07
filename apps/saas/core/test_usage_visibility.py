from django.test import TestCase
from rest_framework.test import APIClient

from .models import Entitlement, Membership, UsageCounter, User
from .services import create_workspace
from .usage import reserve_usage, settle_usage


class UsageVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="visibility")
        self.workspace = create_workspace(self.user, {"name": "A", "timezone": "UTC"})
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.api = f"/api/v1/workspaces/{self.workspace.id}/usage/"
        self.page = f"/workspaces/{self.workspace.id}/usage/"

    def test_missing_entitlements_fail_closed_without_creating_balances(self):
        response = self.client.get(self.api)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["entitlement_active"])
        self.assertIsNone(response.data["period"])
        self.assertIsNone(response.data["reset_at"])
        self.assertEqual(
            response.data["counters"]["leads"], {"settled": 0, "reserved": 0, "limit": 0}
        )
        self.assertFalse(Entitlement.objects.exists())
        self.assertFalse(UsageCounter.objects.exists())

    def test_settled_reserved_and_limits_are_server_derived_and_tenant_scoped(self):
        Entitlement.objects.create(
            workspace=self.workspace, active=True, lead_limit=10, job_limit=2
        )
        first = reserve_usage(self.user, self.workspace.id, "first", {"leads": 6, "jobs": 1})
        settle_usage(self.user, self.workspace.id, first.id, {"leads": 3, "jobs": 1})
        reserve_usage(self.user, self.workspace.id, "pending", {"leads": 5})
        other = User.objects.create_user(username="other")
        foreign = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        Entitlement.objects.create(workspace=foreign, active=True, lead_limit=1000)
        reserve_usage(other, foreign.id, "foreign", {"leads": 999})
        response = self.client.get(self.api)
        self.assertEqual(
            response.data["counters"]["leads"], {"settled": 3, "reserved": 5, "limit": 10}
        )
        self.assertEqual(
            response.data["counters"]["jobs"], {"settled": 1, "reserved": 0, "limit": 2}
        )
        self.assertEqual(
            self.client.get(f"/api/v1/workspaces/{foreign.id}/usage/").status_code, 404
        )

    def test_viewers_can_read_but_no_client_mutation_is_exposed(self):
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.client.get(self.api).status_code, 200)
        for method in (self.client.post, self.client.patch, self.client.delete):
            self.assertEqual(method(self.api, {"leads": 1000}, format="json").status_code, 405)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.api).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.api).status_code, 403)

    def test_session_page_is_read_only_escaped_and_requires_membership(self):
        self.workspace.name = "<script>alert(1)</script>"
        self.workspace.save()
        self.assertEqual(self.client.get(self.page).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(self.page)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "No billing period or reset date is configured")
        self.assertContains(response, '<th scope="col">Reserved</th>')
        self.assertEqual(self.client.post(self.page, {"leads": 1000}).status_code, 405)
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.client.get(self.page).status_code, 404)
