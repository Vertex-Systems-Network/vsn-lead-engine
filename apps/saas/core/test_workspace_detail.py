"""Exact workspace detail is read-only and never reveals foreign membership."""

from django.test import TestCase

from .models import Membership, User
from .services import create_workspace


class WorkspaceDetailTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="identity-owner")
        self.viewer = User.objects.create_user(username="identity-viewer")
        self.outsider = User.objects.create_user(username="identity-outsider")
        self.workspace = create_workspace(
            self.owner,
            {"name": "Private workspace marker", "timezone": "America/Toronto"},
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        self.path = f"/api/v1/workspaces/{self.workspace.id}/"

    def test_owner_and_viewer_can_read_exact_workspace_name_and_timezone(self):
        for actor in (self.owner, self.viewer):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                response = self.client.get(self.path)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["id"], str(self.workspace.id))
                self.assertEqual(body["name"], "Private workspace marker")
                self.assertEqual(body["timezone"], "America/Toronto")
                self.assertNotIn("email", body)
                self.assertNotIn("members", body)
                self.assertIn("no-store", response["Cache-Control"])

    def test_anonymous_and_foreign_requests_leak_no_workspace_identity(self):
        anonymous = self.client.get(self.path)
        self.assertIn(anonymous.status_code, (401, 403))
        self.assertNotIn(b"Private workspace marker", anonymous.content)
        self.client.force_login(self.outsider)
        foreign = self.client.get(self.path)
        self.assertEqual(foreign.status_code, 404)
        self.assertNotIn(b"Private workspace marker", foreign.content)

    def test_revoked_membership_loses_read_access(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        Membership.objects.filter(workspace=self.workspace, user=self.viewer).delete()
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_detail_does_not_accept_write_verbs(self):
        self.client.force_login(self.owner)
        for method in ("post", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.path, {"name": "Forged new name"})
                self.assertEqual(response.status_code, 405)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Private workspace marker")
