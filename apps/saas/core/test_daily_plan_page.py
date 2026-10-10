"""Browser daily plans are disabled, CSRF-protected and source-draft bound."""

from django.test import Client, TestCase

from .daily_plan_forms import new_daily_plan_token
from .models import DailySchedule, Job, Membership, ScheduleOccurrence, User
from .serializers import SearchSerializer
from .services import create_draft, create_workspace


class DailyPlanPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="plan-save-owner")
        self.viewer = User.objects.create_user(username="plan-save-viewer")
        self.other = User.objects.create_user(username="plan-save-other")
        self.workspace = create_workspace(
            self.owner, {"name": "Owned draft scope", "timezone": "America/Toronto"}
        )
        self.foreign = create_workspace(
            self.other, {"name": "Foreign draft scope", "timezone": "America/New_York"}
        )
        Membership.objects.create(workspace=self.workspace, user=self.viewer, role="viewer")
        search = SearchSerializer(
            data={
                "countries": ["CA"],
                "categories": ["Synthetic bakery"],
                "result_limit": 25,
            }
        )
        search.is_valid(raise_exception=True)
        self.draft, _ = create_draft(
            self.owner, self.workspace.id, search.validated_data, "daily-plan-origin"
        )
        self.path = f"/workspaces/{self.workspace.id}/jobs/{self.draft.id}/daily-plan/"
        self.client = Client(enforce_csrf_checks=True)

    def form(self, actor=None):
        actor = actor or self.owner
        self.client.force_login(actor)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        return {
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            "plan_token": new_daily_plan_token(actor, self.workspace.id, self.draft.id),
            "timezone": "America/Toronto",
            "time": "08:15",
        }

    def test_create_and_exact_replay_never_enable_any_execution(self):
        payload = self.form()
        created = self.client.post(self.path, payload)
        self.assertEqual(created.status_code, 201)
        self.assertContains(created, "Disabled — no runs scheduled", status_code=201)
        self.assertContains(created, "Synthetic bakery", status_code=201)
        plan = DailySchedule.objects.get()
        self.assertEqual(plan.workspace_id, self.workspace.id)
        self.assertEqual(plan.created_by_id, self.owner.id)
        self.assertEqual(plan.search, self.draft.search)
        self.assertEqual(plan.local_time.strftime("%H:%M"), "08:15")
        self.assertFalse(plan.enabled)
        self.assertEqual(plan.revision, 1)
        self.assertEqual(self.client.post(self.path, payload).status_code, 200)
        self.assertEqual(DailySchedule.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse(ScheduleOccurrence.objects.exists())

    def test_reused_key_with_changed_parameters_conflicts_without_new_plan(self):
        payload = self.form()
        self.assertEqual(self.client.post(self.path, payload).status_code, 201)
        different = {**payload, "time": "09:15"}
        response = self.client.post(self.path, different)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "already used", status_code=409)
        self.assertEqual(DailySchedule.objects.count(), 1)
        self.assertFalse(DailySchedule.objects.get().enabled)

    def test_csrf_field_tampering_and_foreign_token_rejected(self):
        self.client.force_login(self.owner)
        # A cross-site POST without a CSRF cookie/token cannot create a plan.
        self.assertEqual(
            self.client.post(
                self.path, {"timezone": "UTC", "time": "08:00", "plan_token": "forged"}
            ).status_code,
            403,
        )
        payload = self.form()
        for changes in (
            {"plan_token": "forged"},
            {"plan_token": new_daily_plan_token(self.other, self.workspace.id, self.draft.id)},
            {"timezone": "Fake/Timezone"},
            {"time": "29:00"},
            {"enabled": "1"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post(self.path, {**payload, **changes}).status_code,
                    400,
                )
        self.assertFalse(DailySchedule.objects.exists())

    def test_viewer_foreign_and_revoked_membership_cannot_save(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.client.force_login(self.owner)
        payload = self.form()
        Membership.objects.filter(workspace=self.workspace, user=self.owner).delete()
        self.assertEqual(self.client.post(self.path, payload).status_code, 404)
        self.assertFalse(DailySchedule.objects.exists())

    def test_get_query_unsupported_and_non_draft_origin_refused(self):
        payload = self.form()
        self.assertEqual(self.client.get(self.path + "?timezone=UTC").status_code, 400)
        # CSRF middleware can reject an unsafe verb before the view's
        # method allowlist; both 403 and 405 must leave plans untouched.
        self.assertIn(self.client.put(self.path, payload).status_code, (403, 405))
        Job.objects.filter(pk=self.draft.id).update(status="queued")
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.client.post(self.path, payload).status_code, 404)
        self.assertFalse(DailySchedule.objects.exists())
