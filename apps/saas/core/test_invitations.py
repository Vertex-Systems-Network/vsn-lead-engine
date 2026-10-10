"""Existing-account invitations: scoped authorisation, one-use secrets, no email."""

from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from .models import Membership, MembershipAudit, User, WorkspaceInvitation
from .services import create_workspace


class WorkspaceInvitationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="invite-owner")
        self.admin = User.objects.create_user(username="invite-admin")
        self.member = User.objects.create_user(username="invite-member")
        self.recipient = User.objects.create_user(username="invite-recipient")
        self.other = User.objects.create_user(username="invite-other")
        self.foreign_owner = User.objects.create_user(username="invite-foreign")
        self.workspace = create_workspace(
            self.owner, {"name": "Private invites", "timezone": "UTC"}
        )
        self.foreign = create_workspace(
            self.foreign_owner, {"name": "Foreign private invites", "timezone": "UTC"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.admin, role="admin")
        Membership.objects.create(workspace=self.workspace, user=self.member, role="member")
        self.issue_path = f"/workspaces/{self.workspace.pk}/invitations/new/"
        self.accept_path = "/accounts/accept-invitation/"
        self.client = Client(enforce_csrf_checks=True)

    def issue_form(self, actor=None, path=None, role="member", username="invite-recipient"):
        self.client.force_login(actor or self.owner)
        result = self.client.get(path or self.issue_path)
        self.assertEqual(result.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "confirmation_token": result.context["form"]["confirmation_token"].value(),
            "username": username,
            "role": role,
        }

    def issued_code(self, actor=None, role="member"):
        body = self.issue_form(actor=actor, role=role)
        response = self.client.post(self.issue_path, body)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertContains(response, "Copy this code now")
        self.assertNotContains(response, "Foreign private invites")
        self.assertEqual(mail.outbox, [])
        invitation = WorkspaceInvitation.objects.get()
        return response.context["code"], invitation

    def accept(self, actor, code):
        self.client.force_login(actor)
        self.assertEqual(self.client.get(self.accept_path).status_code, 200)
        return self.client.post(
            self.accept_path,
            {
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
                "code": code,
            },
        )

    def test_owner_invite_redeemed_once_by_exact_target_and_audited(self):
        code, invitation = self.issued_code()
        self.assertGreaterEqual(len(code), 40)
        self.assertNotEqual(invitation.token_hash, code)
        self.assertNotIn(code, invitation.token_hash)
        self.assertEqual(MembershipAudit.objects.count(), 0)
        result = self.accept(self.recipient, code)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Workspace invitation accepted")
        self.assertNotIn(code, result.content.decode())
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.recipient).role, "member"
        )
        audit = MembershipAudit.objects.get()
        self.assertEqual(audit.action, "invite_accepted")
        self.assertEqual(audit.target_user_id, self.recipient.pk)
        self.assertEqual(audit.actor_id, self.recipient.pk)
        self.assertEqual(audit.new_role, "member")
        self.assertIsNotNone(WorkspaceInvitation.objects.get(pk=invitation.pk).accepted_at)
        self.assertEqual(self.accept(self.recipient, code).status_code, 400)
        self.assertEqual(MembershipAudit.objects.count(), 1)

    def test_other_account_wrong_workspace_and_code_not_in_get(self):
        code, _ = self.issued_code()
        self.assertEqual(self.accept(self.other, code).status_code, 400)
        self.assertFalse(
            Membership.objects.filter(workspace=self.workspace, user=self.other).exists()
        )
        self.client.force_login(self.foreign_owner)
        self.assertEqual(self.client.get(self.issue_path).status_code, 404)
        self.assertEqual(self.client.get(self.accept_path + "?code=" + code).status_code, 400)
        self.assertNotIn(code, self.client.get(self.accept_path).content.decode())
        self.assertEqual(self.accept(self.recipient, code).status_code, 200)
        self.assertEqual(MembershipAudit.objects.count(), 1)

    def test_non_admin_denied_owner_invites_admin_may_only_invite_member_or_viewer(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.issue_path).status_code, 403)
        self.client.force_login(self.foreign_owner)
        self.assertEqual(self.client.get(self.issue_path).status_code, 404)
        payload = self.issue_form(actor=self.admin)
        self.assertEqual(
            self.client.post(self.issue_path, {**payload, "role": "admin"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(self.issue_path, {**payload, "role": "owner"}).status_code, 400
        )
        self.assertEqual(self.client.post(self.issue_path, payload).status_code, 200)
        self.assertEqual(WorkspaceInvitation.objects.get().role, "member")

    def test_owner_can_invite_admin_and_revoked_inviter_does_not_grant(self):
        code, _ = self.issued_code(role="admin")
        self.assertEqual(WorkspaceInvitation.objects.get().role, "admin")
        self.assertEqual(self.accept(self.recipient, code).status_code, 200)
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.recipient).role, "admin"
        )
        Membership.objects.filter(workspace=self.workspace, user=self.recipient).delete()
        WorkspaceInvitation.objects.all().delete()
        code, _ = self.issued_code(actor=self.admin, role="member")
        Membership.objects.filter(workspace=self.workspace, user=self.admin).delete()
        self.assertEqual(self.accept(self.recipient, code).status_code, 400)
        self.assertFalse(
            Membership.objects.filter(workspace=self.workspace, user=self.recipient).exists()
        )

    def test_expiration_duplicate_and_existing_membership_denied(self):
        code, invitation = self.issued_code()
        body = self.issue_form()
        self.assertEqual(self.client.post(self.issue_path, body).status_code, 409)
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])
        self.assertEqual(self.accept(self.recipient, code).status_code, 400)
        self.assertFalse(
            Membership.objects.filter(workspace=self.workspace, user=self.recipient).exists()
        )
        code2, _ = self.issued_code()
        Membership.objects.create(workspace=self.workspace, user=self.recipient, role="viewer")
        self.assertEqual(self.accept(self.recipient, code2).status_code, 400)

    def test_missing_csrf_forged_review_unknown_username_and_extra_fields(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(
                self.issue_path, {"username": "invite-recipient", "role": "member"}
            ).status_code,
            403,
        )
        payload = self.issue_form()
        self.assertEqual(
            self.client.post(
                self.issue_path, {**payload, "confirmation_token": "forged"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(self.issue_path, {**payload, "override": "owner"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.issue_path, {**payload, "username": "does-not-exist"}
            ).status_code,
            409,
        )
        self.assertEqual(WorkspaceInvitation.objects.count(), 0)
        self.client.force_login(self.recipient)
        self.assertEqual(self.client.post(self.accept_path, {"code": "x" * 43}).status_code, 403)
        self.client.get(self.accept_path)
        csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(
            self.client.post(
                self.accept_path,
                {"csrfmiddlewaretoken": csrf, "code": "x" * 43, "role": "owner"},
            ).status_code,
            400,
        )

    def test_private_code_not_repeated_after_unavailable_attempt(self):
        self.client.force_login(self.recipient)
        self.client.get(self.accept_path)
        code = "x" * 43
        response = self.client.post(
            self.accept_path,
            {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value, "code": code},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(code, response.content.decode())

    def test_bounded_pending_invites(self):
        for idx in range(10):
            user = User.objects.create_user(username=f"invite-slot-{idx}")
            body = self.issue_form(username=user.username)
            self.assertEqual(self.client.post(self.issue_path, body).status_code, 200)
        self.assertEqual(WorkspaceInvitation.objects.count(), 10)
        self.assertEqual(self.client.post(self.issue_path, self.issue_form()).status_code, 409)
        self.assertEqual(WorkspaceInvitation.objects.count(), 10)
