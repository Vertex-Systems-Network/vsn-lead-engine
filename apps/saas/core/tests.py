from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Job, Membership, MembershipAudit, User, Workspace
from .services import create_draft, create_workspace


class TenantAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a", password="local-test-password")
        self.other = User.objects.create_user(username="b", password="local-test-password")
        self.workspace = create_workspace(self.user, {"name": "A", "timezone": "UTC"})
        self.foreign = create_workspace(self.other, {"name": "B", "timezone": "UTC"})
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/v1/workspaces/{self.workspace.id}/jobs/"
        self.search = {"countries": ["US"], "categories": ["software"], "result_limit": 20}

    def create(self, key="first", search=None, url=None):
        return self.client.post(
            url or self.url, search or self.search, format="json", HTTP_IDEMPOTENCY_KEY=key
        )

    def test_workspace_list_hides_other_tenants(self):
        response = self.client.get("/api/v1/workspaces/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([x["id"] for x in response.data["results"]], [str(self.workspace.id)])

    def test_workspace_creation_installs_owner_atomically(self):
        response = self.client.post(
            "/api/v1/workspaces/", {"name": "New", "timezone": "Asia/Karachi"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Membership.objects.filter(
                workspace_id=response.data["id"], user=self.user, role="owner"
            ).exists()
        )

    def test_invalid_timezone_rejected_without_partial_workspace(self):
        response = self.client.post(
            "/api/v1/workspaces/", {"name": "Bad", "timezone": "Mars/Base"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Workspace.objects.filter(name="Bad").exists())

    def test_draft_replay_and_conflict(self):
        first = self.create()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["status"], "draft")
        self.assertEqual(first.data["result_count"], 0)
        self.assertIn("phone", first.data["search"]["required_fields"])
        replay = self.create()
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        conflict = self.create(search={**self.search, "result_limit": 30})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    def test_normalized_search_replay(self):
        first = self.create(search={**self.search, "countries": ["US", "CA"]})
        second = self.create(search={**self.search, "countries": ["CA", "US"]})
        self.assertEqual(first.data["id"], second.data["id"])

    def test_viewer_cannot_write(self):
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_revoked_membership_cannot_replay(self):
        self.create()
        Membership.objects.filter(workspace=self.workspace, user=self.user).delete()
        self.assertEqual(self.create().status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_cross_tenant_read_write_and_ids_hidden(self):
        first = self.create()
        foreign_url = f"/api/v1/workspaces/{self.foreign.id}/jobs/"
        self.assertEqual(self.create(url=foreign_url).status_code, 404)
        self.assertEqual(self.client.get(foreign_url + first.data["id"] + "/").status_code, 404)
        self.assertEqual(self.client.get(self.url + str(uuid4()) + "/").status_code, 404)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(foreign_url + first.data["id"] + "/").status_code, 404)
        self.assertEqual(self.client.get(foreign_url).data["results"], [])

    def test_idempotency_key_is_tenant_scoped(self):
        first = self.create()
        self.client.force_authenticate(self.other)
        second = self.create(url=f"/api/v1/workspaces/{self.foreign.id}/jobs/")
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["id"], second.data["id"])

    def test_invalid_inputs_do_not_write(self):
        for change in (
            {"countries": ["GB"]},
            {"result_limit": 0},
            {"workspace_id": str(self.foreign.id)},
            {"status": "queued"},
            {"categories": []},
        ):
            self.assertEqual(self.create(search={**self.search, **change}).status_code, 400)
        self.assertEqual(self.create(key="").status_code, 400)
        self.assertEqual(self.create(key="x" * 129).status_code, 400)
        self.assertEqual(Job.objects.count(), 0)

    def test_bounded_tenant_pagination(self):
        for index in range(27):
            self.create(key=f"job-{index}")
        page = self.client.get(self.url).data
        self.assertEqual(len(page["results"]), 25)
        following = self.client.get(self.url, {"after": page["next"]}).data
        self.assertEqual(len(following["results"]), 2)
        self.assertIsNone(following["next"])
        self.assertEqual(self.client.get(self.url, {"after": "invalid"}).status_code, 400)

    def test_unauthenticated_and_csrf_mutations_fail(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get(self.url).status_code, 403)
        self.assertTrue(client.login(username="a", password="local-test-password"))
        self.assertEqual(
            client.post(
                self.url, self.search, format="json", HTTP_IDEMPOTENCY_KEY="csrf"
            ).status_code,
            403,
        )
        self.assertEqual(Job.objects.count(), 0)

    def test_session_login_logout_and_overview(self):
        client = APIClient(enforce_csrf_checks=True)
        login = client.get("/accounts/login/")
        self.assertContains(login, "csrfmiddlewaretoken")
        token = client.cookies["csrftoken"].value
        response = client.post(
            "/accounts/login/",
            {"username": "a", "password": "local-test-password", "csrfmiddlewaretoken": token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertContains(client.get("/"), "Your workspaces")
        self.assertEqual(client.get("/accounts/logout/").status_code, 405)
        token = client.cookies["csrftoken"].value
        self.assertEqual(
            client.post("/accounts/logout/", {"csrfmiddlewaretoken": token}).status_code, 302
        )
        self.assertEqual(client.get("/").status_code, 302)

    def test_health_is_secret_free_and_provider_disabled(self):
        self.assertEqual(
            self.client.get("/health/").json(),
            {"status": "ok", "service": "vsn-lead-saas", "provider_dispatch": False},
        )

    def test_database_rejects_duplicate_membership_and_invalid_role(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(workspace=self.workspace, user=self.user, role="owner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(workspace=self.foreign, user=self.user, role="invalid")


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentDraftTests(TransactionTestCase):
    def test_concurrent_identical_requests_create_one_draft(self):
        user = User.objects.create_user(username="race")
        workspace = create_workspace(user, {"name": "Race", "timezone": "UTC"})
        barrier = Barrier(2)

        def create():
            close_old_connections()
            try:
                actor = User.objects.get(pk=user.id)
                barrier.wait(timeout=10)
                job, created = create_draft(
                    actor, workspace.id, {"countries": ["US"], "categories": ["software"]}, "same"
                )
                return job.id, created
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(Job.objects.count(), 1)


class MemberLifecycleTests(TestCase):
    setUp = TenantAPITests.setUp
    create = TenantAPITests.create

    def member_url(self, user=None):
        return f"/api/v1/workspaces/{self.workspace.id}/members/{(user or self.user).id}/"

    def test_last_owner_cannot_be_demoted_or_removed(self):
        url = self.member_url()
        self.assertEqual(self.client.patch(url, {"role": "member"}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertEqual(
            Membership.objects.get(workspace=self.workspace, user=self.user).role, "owner"
        )
        self.assertEqual(MembershipAudit.objects.count(), 0)

    def test_owner_can_transfer_then_revoke_own_membership(self):
        Membership.objects.create(workspace=self.workspace, user=self.other, role="member")
        response = self.client.patch(self.member_url(self.other), {"role": "owner"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.delete(self.member_url()).status_code, 204)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(MembershipAudit.objects.count(), 2)
        self.assertEqual(MembershipAudit.objects.latest("id").action, "removed")
        self.assertEqual(
            Membership.objects.filter(workspace=self.workspace, role="owner").count(), 1
        )

    def test_admin_cannot_change_owner_or_promote_self(self):
        Membership.objects.create(workspace=self.workspace, user=self.other, role="admin")
        self.client.force_authenticate(self.other)
        self.assertEqual(
            self.client.patch(self.member_url(), {"role": "viewer"}, format="json").status_code, 403
        )
        self.assertEqual(self.client.delete(self.member_url()).status_code, 403)
        self.assertEqual(
            self.client.patch(
                self.member_url(self.other), {"role": "owner"}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(MembershipAudit.objects.count(), 0)

    def test_member_cannot_manage_members(self):
        Membership.objects.create(workspace=self.workspace, user=self.other, role="member")
        self.client.force_authenticate(self.other)
        self.assertEqual(
            self.client.get(f"/api/v1/workspaces/{self.workspace.id}/members/").status_code, 403
        )
        self.assertEqual(
            self.client.patch(self.member_url(), {"role": "viewer"}, format="json").status_code, 403
        )

    def test_foreign_member_is_hidden(self):
        response = self.client.patch(self.member_url(self.other), {"role": "viewer"}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(MembershipAudit.objects.count(), 0)
        self.assertEqual(self.client.delete(self.member_url(self.other)).status_code, 404)

    def test_role_change_is_audited_once_and_replay_is_noop(self):
        Membership.objects.create(workspace=self.workspace, user=self.other, role="member")
        for _ in range(2):
            response = self.client.patch(
                self.member_url(self.other), {"role": "viewer"}, format="json"
            )
            self.assertEqual(response.status_code, 200)
        audit = MembershipAudit.objects.get()
        self.assertEqual(audit.actor_id, self.user.id)
        self.assertEqual(audit.previous_role, "member")
        self.assertEqual(audit.new_role, "viewer")
        self.assertEqual(
            self.client.patch(
                self.member_url(self.other),
                {"role": "owner", "user_id": str(uuid4())},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                self.member_url(self.other), {"role": "root"}, format="json"
            ).status_code,
            400,
        )


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentOwnerTests(TransactionTestCase):
    def test_two_owners_cannot_concurrently_remove_last_owner(self):
        from rest_framework.exceptions import ValidationError

        from .services import change_membership

        user_a = User.objects.create_user(username="owner-a")
        user_b = User.objects.create_user(username="owner-b")
        workspace = create_workspace(user_a, {"name": "Race", "timezone": "UTC"})
        Membership.objects.create(workspace=workspace, user=user_b, role="owner")
        barrier = Barrier(2)

        def demote(user_id):
            close_old_connections()
            try:
                actor = User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    change_membership(actor, workspace.id, user_id, role="member")
                    return "changed"
                except ValidationError:
                    return "retained"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, [user_a.id, user_b.id]))
        self.assertCountEqual(results, ["changed", "retained"])
        self.assertEqual(Membership.objects.filter(workspace=workspace, role="owner").count(), 1)
        self.assertEqual(MembershipAudit.objects.count(), 1)


class LoginAbuseTests(TestCase):
    def test_ip_and_account_caps_do_not_reveal_or_store_identity(self):
        from .login_security import ACCOUNT_LIMIT, allow_login
        from .models import LoginBucket

        for _ in range(ACCOUNT_LIMIT):
            self.assertTrue(allow_login("private-user", "192.0.2.1"))
        self.assertFalse(allow_login("ＰＲＩＶＡＴＥ－ＵＳＥＲ", "192.0.2.2"))
        self.assertEqual(LoginBucket.objects.count(), 3)
        for row in LoginBucket.objects.all():
            self.assertEqual(len(row.fingerprint), 64)
            self.assertNotIn("private-user", row.fingerprint)
            self.assertNotIn("192.0.2", row.fingerprint)

    def test_ip_cap_survives_username_rotation(self):
        from .login_security import IP_LIMIT, allow_login

        for index in range(IP_LIMIT):
            self.assertTrue(allow_login(f"user-{index}", "192.0.2.1"))
        self.assertFalse(allow_login("different-user", "192.0.2.1"))

    def test_window_reset_and_retention_cleanup(self):
        from datetime import timedelta

        from .login_security import ACCOUNT_LIMIT, RETENTION, WINDOW, allow_login
        from .models import LoginBucket

        now = timezone.now()
        LoginBucket.objects.create(
            fingerprint="a" * 64, started_at=now - RETENTION - timedelta(seconds=1), attempts=2
        )
        for _ in range(ACCOUNT_LIMIT):
            self.assertTrue(allow_login("user", "192.0.2.1", now=now))
        self.assertFalse(allow_login("user", "192.0.2.1", now=now))
        self.assertTrue(allow_login("user", "192.0.2.1", now=now + WINDOW))
        self.assertFalse(LoginBucket.objects.filter(pk="a" * 64).exists())

    def test_login_endpoint_enforces_limit_and_ignores_forwarded_header(self):
        from .login_security import ACCOUNT_LIMIT

        user = User.objects.create_user(username="login-user", password="valid-test-password")
        client = APIClient(enforce_csrf_checks=True)
        client.get("/accounts/login/")
        token = client.cookies["csrftoken"].value
        for _ in range(ACCOUNT_LIMIT):
            response = client.post(
                "/accounts/login/",
                {"username": user.username, "password": "wrong", "csrfmiddlewaretoken": token},
            )
            self.assertEqual(response.status_code, 200)
        response = client.post(
            "/accounts/login/",
            {
                "username": user.username,
                "password": "valid-test-password",
                "csrfmiddlewaretoken": token,
            },
            HTTP_X_FORWARDED_FOR="192.0.2.200",
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)
        self.assertEqual(response["Retry-After"], "900")
        self.assertEqual(client.get("/").status_code, 302)


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentLoginTests(TransactionTestCase):
    def test_concurrent_requests_cannot_exceed_account_budget(self):
        from .login_security import ACCOUNT_LIMIT, allow_login
        from .models import LoginBucket

        for _ in range(ACCOUNT_LIMIT - 1):
            self.assertTrue(allow_login("user", "192.0.2.1"))
        barrier = Barrier(2)

        def attempt(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return allow_login("user", "192.0.2.1")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertCountEqual(results, [True, False])
        self.assertTrue(all(row.attempts <= 20 for row in LoginBucket.objects.all()))


class UsageReservationTests(TestCase):
    def setUp(self):
        from .models import Entitlement

        self.user = User.objects.create_user(username="usage")
        self.workspace = create_workspace(self.user, {"name": "Usage", "timezone": "UTC"})
        self.entitlement = Entitlement.objects.create(
            workspace=self.workspace, active=True, lead_limit=10, job_limit=2
        )

    def test_reserve_replay_conflict_and_limits(self):
        from rest_framework.exceptions import ValidationError

        from .services import IdempotencyConflict
        from .usage import reserve_usage

        first = reserve_usage(self.user, self.workspace.id, "key", {"leads": 8, "jobs": 1})
        replay = reserve_usage(self.user, self.workspace.id, "key", {"jobs": 1, "leads": 8})
        self.assertEqual(first.id, replay.id)
        with self.assertRaises(IdempotencyConflict):
            reserve_usage(self.user, self.workspace.id, "key", {"leads": 9})
        with self.assertRaises(ValidationError):
            reserve_usage(self.user, self.workspace.id, "other", {"leads": 3})

    def test_settlement_is_idempotent_and_unused_capacity_freed(self):
        from rest_framework.exceptions import ValidationError

        from .models import UsageCounter
        from .services import IdempotencyConflict
        from .usage import reserve_usage, settle_usage

        first = reserve_usage(self.user, self.workspace.id, "key", {"leads": 8})
        with self.assertRaises(ValidationError):
            settle_usage(self.user, self.workspace.id, first.id, {"leads": 9})
        for _ in range(2):
            settle_usage(self.user, self.workspace.id, first.id, {"leads": 3})
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 3)
        self.assertIsNotNone(reserve_usage(self.user, self.workspace.id, "next", {"leads": 7}))
        with self.assertRaises(IdempotencyConflict):
            settle_usage(self.user, self.workspace.id, first.id, {"leads": 4})

    def test_release_frees_capacity_without_refunding_settled_use(self):
        from rest_framework.exceptions import ValidationError

        from .usage import release_usage, reserve_usage, settle_usage

        first = reserve_usage(self.user, self.workspace.id, "key", {"leads": 10})
        for _ in range(2):
            release_usage(self.user, self.workspace.id, first.id)
        with self.assertRaises(ValidationError):
            settle_usage(self.user, self.workspace.id, first.id, {"leads": 1})
        second = reserve_usage(self.user, self.workspace.id, "second", {"leads": 10})
        settle_usage(self.user, self.workspace.id, second.id, {"leads": 10})
        with self.assertRaises(ValidationError):
            release_usage(self.user, self.workspace.id, second.id)

    def test_tenant_role_entitlement_and_invalid_amounts_fail_closed(self):
        from django.http import Http404
        from rest_framework.exceptions import PermissionDenied, ValidationError

        from .usage import reserve_usage, settle_usage

        for value in (-1, True, 1.5, 2147483648):
            with self.assertRaises(ValidationError):
                reserve_usage(self.user, self.workspace.id, "bad", {"leads": value})
        with self.assertRaises(ValidationError):
            reserve_usage(self.user, self.workspace.id, "bad", {"client_balance": 100})
        with self.assertRaises(ValidationError):
            reserve_usage(self.user, self.workspace.id, "paid", {"provider_calls": 1})
        first = reserve_usage(self.user, self.workspace.id, "key", {"leads": 1})
        other = User.objects.create_user(username="other")
        foreign = create_workspace(other, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(Http404):
            settle_usage(other, foreign.id, first.id, {"leads": 1})
        self.entitlement.active = False
        self.entitlement.save()
        with self.assertRaises(PermissionDenied):
            reserve_usage(self.user, self.workspace.id, "key", {"leads": 1})
        Membership.objects.filter(workspace=self.workspace, user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            settle_usage(self.user, self.workspace.id, first.id, {"leads": 1})


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locking")
class ConcurrentUsageTests(TransactionTestCase):
    def test_concurrent_reservations_cannot_overspend(self):
        from rest_framework.exceptions import ValidationError

        from .models import Entitlement, UsageReservation
        from .usage import reserve_usage

        user = User.objects.create_user(username="budget")
        workspace = create_workspace(user, {"name": "Budget", "timezone": "UTC"})
        Entitlement.objects.create(workspace=workspace, active=True, lead_limit=10)
        barrier = Barrier(2)

        def reserve(index):
            close_old_connections()
            try:
                actor = User.objects.get(pk=user.id)
                barrier.wait(timeout=10)
                try:
                    reserve_usage(actor, workspace.id, f"key-{index}", {"leads": 7})
                    return "reserved"
                except ValidationError:
                    return "limited"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertCountEqual(results, ["reserved", "limited"])
        self.assertEqual(UsageReservation.objects.count(), 1)
