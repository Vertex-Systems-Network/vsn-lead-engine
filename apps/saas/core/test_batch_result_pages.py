"""The v3 read service stays isolated and checks state and rights on every page."""

from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .batch_result_pages import batch_results_page
from .batch_settlement import settle_batch_job
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    Entitlement,
    SourceBatchTerminal,
    SourcePolicy,
    UsageReservation,
)
from .test_batch_events import SETTINGS
from .test_batch_terminal_events import TERMINAL_KEY, TerminalFixture


@override_settings(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_TERMINAL_EVENTS_ENABLED=True,
    SAAS_BATCH_SETTLEMENT_ENABLED=True,
    SAAS_BATCH_PAGE_READ_ENABLED=True,
    SAAS_BATCH_PAGE_SIGNING_KEY="test-page-key-with-at-least-32-bytes",
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_TERMINAL_VERIFIERS={"fixture": {"terminal": TERMINAL_KEY}},
)
class BatchResultPageTests(TerminalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.terminal()

    def read(self, cursor=None, **filters):
        return batch_results_page(
            self.user, self.operation.workspace_id, self.operation.job_id, cursor, **filters
        )

    def settle(self):
        settle_batch_job(
            self.user,
            self.operation.workspace_id,
            self.operation.job_id,
            {self.operation.pk: self.terminal_proof()},
        )

    def test_only_completed_current_rights_result_is_visible(self):
        with self.assertRaises(PermissionDenied):
            with override_settings(SAAS_BATCH_PAGE_READ_ENABLED=False):
                self.read()
        with override_settings(SAAS_BATCH_PAGE_SIGNING_KEY=""):
            with self.assertRaises(ValidationError):
                self.read()
        self.settle()
        page = self.read()
        self.assertEqual(len(page["results"]), 1)
        self.assertEqual(page["withheld_count"], 0)
        self.assertIsNone(page["next_cursor"])
        self.assertNotIn("record_ref", page["results"][0])
        self.assertFalse(page["can_review_export"])
        self.assertEqual(len(self.read(country="CA")["results"]), 0)
        self.assertEqual(len(self.read(category="0", source="0")["results"]), 1)

    def test_incomplete_job_entitlement_and_policy_revocation_fail_closed(self):
        from .jobs import RevisionConflict

        with self.assertRaises(RevisionConflict):
            self.read()
        self.settle()
        Entitlement.objects.filter(workspace_id=self.operation.workspace_id).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.read()
        Entitlement.objects.filter(workspace_id=self.operation.workspace_id).update(active=True)
        SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
        with self.assertRaises(PermissionDenied):
            self.read()

    def test_expired_result_is_withheld_and_bad_filter_rejected(self):
        from django.utils import timezone

        self.settle()
        AcceptedResult.objects.filter(job=self.operation.job).update(delete_at=timezone.now())
        page = self.read()
        self.assertEqual(page["results"], [])
        self.assertEqual(page["withheld_count"], 1)
        with self.assertRaises(ValidationError):
            self.read(category="11")

    def test_row_count_corruption_does_not_expose_partial_pages(self):
        from .jobs import RevisionConflict

        self.settle()
        AcceptedFingerprint.objects.filter(result__job=self.operation.job).delete()
        AcceptedResult.objects.filter(job=self.operation.job).delete()
        with self.assertRaises(RevisionConflict):
            self.read()

    def test_settlement_and_source_final_drift_deny_page(self):
        from .jobs import RevisionConflict

        self.settle()
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        reservation.settlement = {**reservation.settlement, "provider_calls": 0}
        reservation.save(update_fields=["settlement"])
        with self.assertRaises(RevisionConflict):
            self.read()
        reservation.settlement = {**reservation.settlement, "provider_calls": 1}
        reservation.save(update_fields=["settlement"])
        SourceBatchTerminal.objects.filter(operation=self.operation).update(accepted_count=2)
        with self.assertRaises(RevisionConflict):
            self.read()
