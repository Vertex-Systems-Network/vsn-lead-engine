"""Explicit member role changes have fresh CSRF, signed scope and history fences."""

from django.test import Client, TestCase

from .member_role_forms import new_role_token
from .models import Membership, MembershipAudit, User
from .services import change_membership, create_workspace


class MemberRoleChangePageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="role-form-owner")
        self.admin = User.objects.create_user(username="role-form-admin")
        self.member = User.objects.create_user(username="role-form-member")
        self.viewer = User.objects.create_user(username="role-form-viewer")
        self.foreign_user = User.objects.create_user(username="role-form-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private role form", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_user, {"name": "Foreign private role form", "timezone": "UTC"}
        )
        for user, role in (
            (self.admin, "admin"),
            (self.member, "member"),
            (self.viewer, "viewer"),
        ):
            Membership.objects.create(workspace=self.workspace, user=user, role=role)
        self.path = (
            f"/workspaces/{self.workspace.id}/members/{self.member.id}/role/"
        )
        self.client = Client(enforce_csrf_checks=True)

    def payload(self, actor=None, *, path=None, new_role="viewer"):
        self.client.force_login(actor or self.owner)
        response = self.client.get(path or self.path)
        self.assertEqual(response.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "confirmation_token": response.context["form"]["confirmation_token"].value(),
            "new_role": new_role,
        }

    def test_owner_changes_role_once_and_replay_is_a_stale_conflict(self):
        body = self.payload()
        self.assertEqual(MembershipAudit.objects.count(), 0)
        get = self.client.get(self.path)
        self.assertContains(get, "Confirm member role change")
        self.assertIn("no-store", get["Cache-Control"])
        response = self.client.post(self.path, body)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member role changed")
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.member).role,
            "viewer",
        )
        audit = MembershipAudit.objects.get()
        self.assertEqual(audit.actor_id, self.owner.id)
        self.assertEqual(audit.previous_role, "member")
        self.assertEqual(audit.new_role, "viewer")
        self.assertEqual(self.client.post(self.path, body).status_code, 409)
        self.assertEqual(MembershipAudit.objects.count(), 1)
        self.assertNotIn("Foreign private role form", response.content.decode())

    def test_admin_can_downgrade_member_but_cannot_edit_or_create_owner(self):
        body = self.payload(self.admin, new_role="viewer")
        self.assertEqual(self.client.post(self.path, body).status_code, 200)
        self.assertEqual(MembershipAudit.objects.count(), 1)
        owner_path = f"/workspaces/{self.workspace.id}/members/{self.owner.id}/role/"
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(owner_path).status_code, 403)
        self.assertEqual(self.client.post(owner_path, body).status_code, 403)
        self.assertNotIn(
            'value="owner"',
            self.client.get(self.path).content.decode(),
        )

    def test_last_owner_cannot_be_demoted(self):
        owner_path = f"/workspaces/{self.workspace.id}/members/{self.owner.id}/role/"
        body = self.payload(path=owner_path, new_role="member")
        self.assertEqual(self.client.post(owner_path, body).status_code, 400)
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.owner).role,
            "owner",
        )
        self.assertEqual(MembershipAudit.objects.count(), 0)

    def test_current_membership_foreign_and_revocation_requirements(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.foreign_user)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Private role form", response.content.decode())
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.foreign.id}/members/{self.foreign_user.id}/role/"
            ).status_code,
            404,
        )
        body = self.payload()
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.post(self.path, body).status_code, 404)
        self.assertFalse(MembershipAudit.objects.exists())

    def test_csrf_forgery_duplicate_fields_and_aba_replay_are_blocked(self):
        self.client.force_login(self.owner)
        forged = {
            "new_role": "viewer",
            "confirmation_token": new_role_token(
                self.owner, self.workspace.id, self.member.id, "member"
            ),
        }
        self.assertEqual(self.client.post(self.path, forged).status_code, 403)
        body = self.payload()
        self.assertEqual(
            self.client.post(self.path, {**body, "confirmation_token": "tampered"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(self.path, {**body, "remove": "true"}).status_code,
            400,
        )
        self.assertEqual(self.client.get(self.path + "?role=owner").status_code, 400)
        self.assertEqual(self.client.put(self.path, {}).status_code, 405)
        change_membership(self.owner, self.workspace.id, self.member.id, role="viewer")
        change_membership(self.owner, self.workspace.id, self.member.id, role="member")
        self.assertEqual(self.client.post(self.path, body).status_code, 409)
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.member).role,
            "member",
        )
        self.assertEqual(MembershipAudit.objects.count(), 2)
