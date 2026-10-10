"""Pending invitation revocation never grants or removes membership."""

import uuid
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from .invitations import InvitationUnavailable, issue_invitation, redeem_invitation
from .models import Membership, MembershipAudit, User, WorkspaceInvitation
from .services import create_workspace


class InvitationRevocationPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="revoke-invite-owner")
        self.admin = User.objects.create_user(username="revoke-invite-admin")
        self.viewer = User.objects.create_user(username="revoke-invite-viewer")
        self.target = User.objects.create_user(username="revoke-invite-target")
        self.foreign_owner = User.objects.create_user(username="revoke-invite-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Invite revocations", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_owner, {"name": "Other invite revocations", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.admin, role="admin")
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.invitation, self.code = issue_invitation(
            self.owner, self.workspace.id, self.target.username, "member"
        )
        self.list_path = f"/workspaces/{self.workspace.id}/invitations/"
        self.revoke_path = (
            f"/workspaces/{self.workspace.id}/invitations/{self.invitation.id}/revoke/"
        )
        self.client = Client(enforce_csrf_checks=True)

    def review(self, actor=None, path=None):
        self.client.force_login(actor or self.owner)
        response = self.client.get(path or self.revoke_path)
        self.assertEqual(response.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "confirmation_token": response.context["form"]["confirmation_token"].value(),
            "confirm_revocation": "on",
        }

    def test_owner_revokes_unused_code_once_without_member_mutation(self):
        self.client.force_login(self.owner)
        pending = self.client.get(self.list_path)
        self.assertEqual(pending.status_code, 200)
        self.assertIn("no-store", pending["Cache-Control"])
        self.assertNotIn(self.code, pending.content.decode())
        self.assertNotIn(self.invitation.token_hash, pending.content.decode())
        self.assertContains(pending, self.target.username)
        claim = self.review()
        self.assertEqual(MembershipAudit.objects.count(), 0)
        self.assertEqual(self.client.post(self.revoke_path, claim).status_code, 200)
        self.assertIsNotNone(
            WorkspaceInvitation.objects.get(pk=self.invitation.pk).revoked_at
        )
        self.assertFalse(
            Membership.objects.filter(workspace=self.workspace, user=self.target).exists()
        )
        audit = MembershipAudit.objects.get()
        self.assertEqual(audit.action, "invite_revoked")
        self.assertEqual(audit.actor_id, self.owner.id)
        self.assertEqual(audit.target_user_id, self.target.id)
        self.assertEqual(audit.previous_role, "")
        self.assertEqual(audit.new_role, "")
        with self.assertRaises(InvitationUnavailable):
            redeem_invitation(self.target, self.code)
        self.assertEqual(self.client.post(self.revoke_path, claim).status_code, 409)
        self.assertEqual(MembershipAudit.objects.count(), 1)
        self.assertNotContains(self.client.get(self.list_path), self.target.username)

    def test_revoke_is_not_member_removal_when_already_accepted(self):
        claim = self.review()
        redeemed = redeem_invitation(self.target, self.code)
        self.assertIsNotNone(redeemed.accepted_at)
        self.assertEqual(self.client.post(self.revoke_path, claim).status_code, 409)
        self.assertTrue(
            Membership.objects.filter(workspace=self.workspace, user=self.target).exists()
        )
        self.assertEqual(
            list(MembershipAudit.objects.values_list("action", flat=True)), ["invite_accepted"]
        )

    def test_viewer_foreign_user_revoked_actor_and_unknown_id_denied(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.list_path).status_code, 403)
        self.assertEqual(self.client.get(self.revoke_path).status_code, 403)
        self.client.force_login(self.foreign_owner)
        self.assertEqual(self.client.get(self.list_path).status_code, 404)
        self.assertEqual(self.client.get(self.revoke_path).status_code, 404)
        claim = self.review()
        self.assertEqual(
            self.client.get(
                f"/workspaces/{self.workspace.id}/invitations/{uuid.uuid4()}/revoke/"
            ).status_code,
            404,
        )
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.post(self.revoke_path, claim).status_code, 404)
        self.assertIsNone(WorkspaceInvitation.objects.get().revoked_at)

    def test_admin_can_revoke_member_invite_but_not_owner_issued_admin_invite(self):
        claim = self.review(actor=self.admin)
        self.assertEqual(self.client.post(self.revoke_path, claim).status_code, 200)
        self.invitation, self.code = issue_invitation(
            self.owner,
            self.workspace.id,
            User.objects.create_user(username="revoke-admin-target").username,
            "admin",
        )
        admin_path = f"/workspaces/{self.workspace.id}/invitations/{self.invitation.id}/revoke/"
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(admin_path).status_code, 403)
        page = self.client.get(self.list_path)
        self.assertContains(page, "Owner only")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(admin_path).status_code, 200)

    def test_expired_or_revoked_pending_never_reissues_review(self):
        self.invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.invitation.save(update_fields=["expires_at"])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.revoke_path).status_code, 409)
        self.assertEqual(MembershipAudit.objects.count(), 0)

    def test_csrf_confirmation_unknown_fields_wrong_scope_and_query_are_denied(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                self.revoke_path,
                {"confirm_revocation": "on", "confirmation_token": "forged"},
            ).status_code,
            403,
        )
        claim = self.review()
        self.assertEqual(
            self.client.post(
                self.revoke_path, {**claim, "confirm_revocation": ""}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.revoke_path, {**claim, "confirmation_token": "forged"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(self.revoke_path, {**claim, "grant_role": "owner"}).status_code,
            400,
        )
        self.assertEqual(self.client.get(self.revoke_path + "?code=forged").status_code, 400)
        self.assertEqual(self.client.get(self.list_path + "?all=1").status_code, 400)
        self.assertIsNone(WorkspaceInvitation.objects.get().revoked_at)
        self.assertEqual(MembershipAudit.objects.count(), 0)
