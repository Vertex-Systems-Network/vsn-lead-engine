from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_allocation import allocate_result_batch
from .jobs import RevisionConflict
from .models import (
    DispatchOperation,
    Entitlement,
    JobOutbox,
    Membership,
    ResultBatch,
    SourceBatchTerminal,
    SourcePolicy,
    User,
)
from .test_batch_models import setup_operation, terminal_values


def fixture():
    operation = setup_operation()
    # Fixture-only future started v3 context. Runtime enrollment cannot start it.
    JobOutbox.objects.filter(pk=operation.outbox_id).update(result_protocol=3)
    return operation.outbox.submitted_by, operation


SETTINGS = {
    "SAAS_BATCH_ALLOCATION_ENABLED": True,
    "SAAS_BATCH_ENROLLMENT_SOURCES": frozenset({"fixture"}),
}


@override_settings(**SETTINGS)
class BatchAllocationTests(TestCase):
    def setUp(self):
        self.user, self.operation = fixture()
        self.workspace_id = self.operation.workspace_id

    def allocate(self, ordinal=1):
        return allocate_result_batch(self.user, self.workspace_id, self.operation.id, ordinal)

    def test_default_disabled_v2_and_empty_source_gates_preserve_capacity(self):
        for options in (
            {"SAAS_BATCH_ALLOCATION_ENABLED": False},
            {"SAAS_BATCH_ENROLLMENT_SOURCES": frozenset()},
        ):
            with override_settings(**options), self.assertRaises(PermissionDenied):
                self.allocate()
        JobOutbox.objects.filter(pk=self.operation.outbox_id).update(result_protocol=2)
        with self.assertRaises(RevisionConflict):
            self.allocate()
        self.assertFalse(ResultBatch.objects.exists())

    def test_server_uuid_contiguous_ordinals_exact_replay_and_no_accounting(self):
        first, created = self.allocate()
        same, replay = self.allocate()
        second, _ = self.allocate(2)
        self.assertTrue(created)
        self.assertFalse(replay)
        self.assertEqual(first.pk, same.pk)
        self.assertNotEqual(first.pk, second.pk)
        self.operation.outbox.reservation.refresh_from_db()
        self.operation.job.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
        self.assertEqual(
            (self.operation.job.status, self.operation.job.result_count), ("running", 0)
        )
        self.assertFalse(self.operation.job.acceptedresult_set.exists())

    def test_boolean_zero_oversized_and_gapped_ordinal_denied(self):
        for ordinal in (True, 0, 1001, 1.0):
            with self.assertRaises(ValidationError):
                self.allocate(ordinal)
        with self.assertRaises(RevisionConflict):
            self.allocate(2)
        ResultBatch.objects.create(operation=self.operation, ordinal=2)
        with self.assertRaises(RevisionConflict):
            self.allocate()

    def test_source_slots_exhaust_original_call_capacity(self):
        self.allocate()
        self.allocate(2)
        with self.assertRaises(ValidationError):
            self.allocate(3)
        self.assertEqual(ResultBatch.objects.count(), 2)

    def test_unknown_replays_identity_but_cannot_allocate_more_or_refund(self):
        first, _ = self.allocate()
        from django.utils import timezone

        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        self.assertEqual(self.allocate()[0].pk, first.pk)
        with self.assertRaises(RevisionConflict):
            self.allocate(2)
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")

    def test_terminal_or_changed_request_policy_and_call_limit_deny(self):
        SourcePolicy.objects.filter(pk="fixture").update(version=2)
        with self.assertRaises(RevisionConflict):
            self.allocate()
        SourcePolicy.objects.filter(pk="fixture").update(version=1)
        DispatchOperation.objects.filter(pk=self.operation.pk).update(call_limit=3)
        with self.assertRaises(RevisionConflict):
            self.allocate()
        DispatchOperation.objects.filter(pk=self.operation.pk).update(call_limit=2)
        SourceBatchTerminal.objects.create(
            **terminal_values(self.operation, batch_count=0, accepted_count=0, provider_calls=0)
        )
        with self.assertRaises(RevisionConflict):
            self.allocate()

    def test_current_role_active_actor_and_grant_caps_are_required(self):
        Membership.objects.filter(user=self.user).update(role="viewer")
        with self.assertRaises(PermissionDenied):
            self.allocate()
        Membership.objects.filter(user=self.user).update(role="owner")
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.allocate()
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        Entitlement.objects.filter(workspace_id=self.workspace_id).update(lead_limit=1)
        with self.assertRaises(PermissionDenied):
            self.allocate()
        self.assertFalse(ResultBatch.objects.exists())

    def test_atomic_insert_failure_leaves_no_identity_or_changed_job(self):
        with patch(
            "core.batch_allocation.ResultBatch.objects.create",
            side_effect=IntegrityError("injected"),
        ):
            with self.assertRaises(IntegrityError):
                self.allocate()
        self.assertFalse(ResultBatch.objects.exists())
        self.operation.job.refresh_from_db()
        self.assertEqual(self.operation.job.revision, 2)

    def test_aggregate_identity_slots_cannot_exceed_original_lead_budget(self):
        # Synthetic corruption beyond the future API allocation ceiling. Even if
        # another source supplies these identities, the entire outbox is counted.
        ResultBatch.objects.bulk_create(
            [ResultBatch(operation=self.operation, ordinal=i) for i in range(1, 11)]
        )
        with self.assertRaises(RevisionConflict):
            self.allocate(11)
        self.assertEqual(ResultBatch.objects.count(), 10)


@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL batch-allocation races required")
@override_settings(**SETTINGS)
class BatchAllocationRaceTests(TransactionTestCase):
    def setUp(self):
        self.user, self.operation = fixture()

    def race(self, actions):
        barrier = Barrier(2)

        def run(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return action()
            except (PermissionDenied, RevisionConflict):
                return "denied"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, actions))

    def allocate(self):
        return allocate_result_batch(self.user, self.operation.workspace_id, self.operation.pk, 1)[
            1
        ]

    def test_duplicate_slot_is_created_once_and_exactly_replayed(self):
        self.assertCountEqual(self.race([self.allocate, self.allocate]), [True, False])
        self.assertEqual(ResultBatch.objects.count(), 1)

    def test_cap_downgrade_and_allocation_serialize(self):
        from django.db import transaction

        from .models import Workspace

        def downgrade():
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=self.operation.workspace_id)
                Entitlement.objects.filter(workspace_id=self.operation.workspace_id).update(
                    lead_limit=0
                )
            return "downgraded"

        outcomes = self.race([self.allocate, downgrade])
        self.assertIn("downgraded", outcomes)
        self.assertEqual(ResultBatch.objects.count(), int(True in outcomes))
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")

    def test_source_revocation_and_allocation_serialize(self):
        from django.db import transaction

        from .models import Workspace

        def revoke():
            with transaction.atomic():
                Workspace.objects.select_for_update().get(pk=self.operation.workspace_id)
                SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
            return "revoked"

        outcomes = self.race([self.allocate, revoke])
        self.assertIn("revoked", outcomes)
        self.assertEqual(ResultBatch.objects.count(), int(True in outcomes))
        self.operation.outbox.reservation.refresh_from_db()
        self.assertEqual(self.operation.outbox.reservation.status, "reserved")
