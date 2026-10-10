"""Owner/admin-only membership audit review; no cross-tenant or mutation effects."""

from django.test import TestCase

from .models import Membership, MembershipAudit, User
from .services import change_membership, create_workspace


class MemberAuditHistoryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="audit-history-owner")
        self.admin = User.objects.create_user(username="audit-history-admin")
        self.viewer = User.objects.create_user(username="audit-history-viewer")
        self.other = User.objects.create_user(username="audit-history-other")
        self.workspace = create_workspace(self.owner, {"name": "Own audit", "timezone": "UTC"})
        self.foreign = create_workspace(
            self.other, {"name": "Foreign private marker", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.admin, role="admin")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="member")
        self.path = f"/api/v1/workspaces/{self.workspace.id}/member-audit/"
        self.foreign_path = f"/api/v1/workspaces/{self.foreign.id}/member-audit/"

    def test_real_role_change_is_visible_only_to_authorized_tenant_members(self):
        change_membership(self.owner, self.workspace.id, self.viewer.id, role="viewer")
        self.client.force_login(self.owner)
        first = self.client.get(self.path)
        self.assertEqual(first.status_code, 200)
        self.assertIn("no-store", first["Cache-Control"])
        self.assertEqual(first.json()["count"], 1)
        event = first.json()["results"][0]
        self.assertEqual(event["action"], "role_changed")
        self.assertEqual(event["actor_user_id"], str(self.owner.id))
        self.assertEqual(event["target_user_id"], str(self.viewer.id))
        self.assertEqual(event["previous_role"], "member")
        self.assertEqual(event["new_role"], "viewer")
        self.assertNotIn("Foreign private marker", first.content.decode())
        self.assertNotIn("email", event)
        self.assertNotIn("password", event)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.path).json()["results"], [event])
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(MembershipAudit.objects.count(), 1)

    def test_foreign_revoked_anonymous_and_writes_are_denied(self):
        MembershipAudit.objects.create(
            workspace=self.foreign,
            actor=self.other,
            target_user_id=self.other.id,
            action="role_changed",
            previous_role="member",
            new_role="admin",
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.foreign_path).status_code, 404)
        self.assertEqual(self.client.get(self.path).json()["count"], 0)
        self.assertEqual(self.client.get(self.path + "?status=all").status_code, 400)
        self.assertEqual(self.client.post(self.path, {}).status_code, 405)
        self.assertEqual(self.client.patch(self.path, {}).status_code, 405)
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.logout()
        self.assertIn(self.client.get(self.path).status_code, (401, 403))
        self.assertEqual(MembershipAudit.objects.count(), 1)

    def test_offset_pages_are_bounded_disjoint_and_read_only(self):
        for i in range(29):
            MembershipAudit.objects.create(
                workspace=self.workspace,
                actor=self.owner,
                target_user_id=self.viewer.id,
                action="removed" if i % 2 else "role_changed",
                previous_role="viewer",
                new_role="" if i % 2 else "member",
            )
        self.client.force_login(self.owner)
        first = self.client.get(self.path).json()
        second = self.client.get(self.path + "?offset=25").json()
        self.assertEqual(first["count"], 29)
        self.assertEqual(second["count"], 29)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 4)
        self.assertIsNotNone(first["next"])
        self.assertIsNone(second["next"])
        self.assertIsNotNone(second["previous"])
        self.assertFalse(
            {row["id"] for row in first["results"]}
            & {row["id"] for row in second["results"]}
        )
        self.assertEqual(MembershipAudit.objects.count(), 29)
