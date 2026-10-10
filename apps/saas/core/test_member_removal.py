"""Removal requires owner/admin, explicit CSRF, signed review and audit history fence."""

from django.test import Client, TestCase

from .models import Membership, MembershipAudit, User
from .services import change_membership, create_workspace


class MemberRemovalPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="remove-form-owner")
        self.admin = User.objects.create_user(username="remove-form-admin")
        self.member = User.objects.create_user(username="remove-form-member")
        self.viewer = User.objects.create_user(username="remove-form-viewer")
        self.foreign_user = User.objects.create_user(username="remove-form-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private member removal", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_user, {"name": "Other private removal", "timezone": "UTC"}
        )
        for user, role in (
            (self.admin, "admin"),
            (self.member, "member"),
            (self.viewer, "viewer"),
        ):
            Membership.objects.create(workspace=self.workspace, user=user, role=role)
        self.path = f"/workspaces/{self.workspace.id}/members/{self.member.id}/remove/"
        self.client = Client(enforce_csrf_checks=True)

    def confirmation(self, actor=None, path=None):
        self.client.force_login(actor or self.owner)
        result = self.client.get(path or self.path)
        self.assertEqual(result.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "removal_token": result.context["form"]["removal_token"].value(),
            "confirm_removal": "on",
        }

    def test_owner_confirmation_removes_only_target_and_records_one_receipt(self):
        claim = self.confirmation()
        page = self.client.get(self.path)
        self.assertContains(page, "Confirm: remove member from this workspace")
        self.assertIn("no-store", page["Cache-Control"])
        self.assertEqual(MembershipAudit.objects.count(), 0)
        result = self.client.post(self.path, claim)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Workspace member removed")
        self.assertFalse(Membership.objects.filter(workspace=self.workspace, user=self.member).exists())
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.owner).exists())
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.admin).exists())
        audit = MembershipAudit.objects.get()
        self.assertEqual(audit.action, "removed")
        self.assertEqual(audit.actor_id, self.owner.id)
        self.assertEqual(audit.target_user_id, self.member.id)
        self.assertEqual(audit.previous_role, "member")
        self.assertEqual(audit.new_role, "")
        self.assertEqual(self.client.post(self.path, claim).status_code, 404)
        self.assertEqual(MembershipAudit.objects.count(), 1)

    def test_admin_may_remove_member_but_never_owner(self):
        claim = self.confirmation(self.admin)
        self.assertEqual(self.client.post(self.path, claim).status_code, 200)
        owner_path = f"/workspaces/{self.workspace.id}/members/{self.owner.id}/remove/"
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(owner_path).status_code, 403)
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.owner).exists())

    def test_last_owner_and_unconfirmed_removals_are_blocked(self):
        path = f"/workspaces/{self.workspace.id}/members/{self.owner.id}/remove/"
        claim = self.confirmation(path=path)
        self.assertEqual(
            self.client.post(path, {**claim, "confirm_removal": ""}).status_code,
            400,
        )
        self.assertEqual(self.client.post(path, claim).status_code, 400)
        self.assertEqual(
            Membership.objects.filter(workspace=self.workspace, role="owner").count(),
            1,
        )
        self.assertFalse(MembershipAudit.objects.exists())

    def test_member_viewer_foreign_revoked_and_invalid_fields_are_denied(self):
        for actor in (self.member, self.viewer):
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.foreign_user)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.foreign.id}/members/{self.foreign_user.id}/remove/"
            ).status_code,
            404,
        )
        claim = self.confirmation()
        self.assertEqual(self.client.get(self.path + "?override=true").status_code, 400)
        self.assertEqual(self.client.post(self.path, {**claim, "delete_account": "yes"}).status_code, 400)
        self.assertEqual(self.client.post(self.path, {**claim, "removal_token": "forged"}).status_code, 400)
        self.assertEqual(
            self.client.put(
                self.path,
                {},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=claim["csrfmiddlewaretoken"],
            ).status_code,
            405,
        )
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.post(self.path, claim).status_code, 404)
        self.assertFalse(MembershipAudit.objects.exists())

    def test_missing_csrf_and_role_aba_after_confirmation_never_remove(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                self.path,
                {"removal_token": "invalid", "confirm_removal": "on"},
            ).status_code,
            403,
        )
        claim = self.confirmation()
        change_membership(self.owner, self.workspace.id, self.member.id, role="viewer")
        change_membership(self.owner, self.workspace.id, self.member.id, role="member")
        self.assertEqual(self.client.post(self.path, claim).status_code, 409)
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.member).exists())
        self.assertEqual(MembershipAudit.objects.count(), 2)
