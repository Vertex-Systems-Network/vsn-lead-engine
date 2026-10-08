import importlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_result_evidence as fixtures
from .attempts import claim_pre_dispatch
from .candidate_events import record_candidate_review
from .dispatch import begin_dispatch
from .jobs import RevisionConflict, enqueue_job
from .models import CandidateEvidence, Entitlement, JobOutbox, Membership, SourcePolicy, User
from .services import IdempotencyConflict, create_draft, create_workspace
from .test_receipts import VERIFIERS


class EventFixture:
    def setUp(self):
        fixtures.CandidateEvidenceTests.setUp(self)

    def signed(self, data=None):
        return fixtures.CandidateEvidenceTests.signed(self, data)

    def record(self, data=None):
        return record_candidate_review(
            self.user, self.workspace.id, self.operation.id, *self.signed(data)
        )

    def unchanged(self):
        fixtures.CandidateEvidenceTests.unchanged(self)

    def other_operation(self):
        workspace = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        Entitlement.objects.create(
            workspace=workspace, active=True, lead_limit=20, job_limit=2, provider_call_limit=4
        )
        job, _ = create_draft(self.user, workspace.id, self.job.search, "other-draft")
        enqueue_job(self.user, workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        lease = claim_pre_dispatch(intent.id)
        operation = begin_dispatch(intent.id, lease.token)[0]
        data = deepcopy(self.data)
        data.update(
            workspace_id=str(workspace.id),
            job_id=str(job.id),
            operation_id=str(operation.id),
            provider_key=str(operation.provider_key),
            request_hash=job.request_hash,
            policy_fingerprint=operation.policy_fingerprint,
        )
        return workspace, operation, data


@override_settings(SAAS_RESULT_VERIFIERS=VERIFIERS)
class CandidateEventTests(EventFixture, TestCase):
    def test_identical_event_replays_one_redacted_record_without_accounting(self):
        first, created = self.record()
        replay, repeated = self.record()
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual((first.pk, first.recorded_at), (replay.pk, replay.recorded_at))
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.assertEqual(first.body_hash, fixtures.CandidateEvidenceTests.review(self).body_hash)
        self.assertEqual(first.candidate_count, 1)
        self.assertEqual(
            set(f.name for f in CandidateEvidence._meta.fields),
            {
                "id",
                "operation",
                "source_code",
                "event_ref",
                "body_hash",
                "candidate_count",
                "earliest_delete_at",
                "recorded_at",
            },
        )
        self.unchanged()

    def test_same_operation_changed_payload_or_event_cannot_replace_evidence(self):
        previous, _ = self.record()
        for key, value in [
            ("event_ref", "second-event"),
            ("issued_at", self.data["issued_at"] + 1),
        ]:
            data = deepcopy(self.data)
            data[key] = value
            with self.assertRaises(IdempotencyConflict):
                self.record(data)
        self.assertEqual(CandidateEvidence.objects.get().body_hash, previous.body_hash)
        self.unchanged()

    def test_source_event_cannot_cross_workspaces_even_with_valid_bound_signature(self):
        self.record()
        workspace, operation, data = self.other_operation()
        with self.assertRaises(IdempotencyConflict):
            record_candidate_review(self.user, workspace.id, operation.id, *self.signed(data))
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.unchanged()

    def test_replay_rechecks_current_role_revocation_and_source_fingerprint(self):
        self.record()
        membership = Membership.objects.get(workspace=self.workspace, user=self.user)
        membership.role = "viewer"
        membership.save()
        with self.assertRaises(PermissionDenied):
            self.record()
        membership.role = "owner"
        membership.save()
        SourcePolicy.objects.filter(pk="fixture").update(version=2)
        with self.assertRaises(RevisionConflict):
            self.record()
        membership.delete()
        with self.assertRaises(Http404):
            self.record()
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.unchanged()

    def test_unsigned_evidence_and_injected_write_failure_leave_no_ledger(self):
        with override_settings(SAAS_RESULT_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.record()
        with patch(
            "core.candidate_events.CandidateEvidence.objects.create",
            side_effect=IntegrityError("injected"),
        ):
            with self.assertRaises(IdempotencyConflict):
                self.record()
        self.assertFalse(CandidateEvidence.objects.exists())
        self.unchanged()

    def test_constraints_protect_parent_and_candidate_evidence_rollback(self):
        guard = importlib.import_module(
            "core.migrations.0012_candidate_evidence"
        ).protect_candidate_rollback
        guard(apps, connection.schema_editor(atomic=False))
        evidence, _ = self.record()
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))
        with self.assertRaises(ProtectedError):
            self.operation.delete()
        for count in [0, 26]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                CandidateEvidence.objects.filter(pk=evidence.pk).update(candidate_count=count)
        self.assertEqual(CandidateEvidence.objects.get().candidate_count, 1)
        self.unchanged()

    def test_expired_replay_does_not_refresh_retention_deadline(self):
        evidence, _ = self.record()
        from django.utils import timezone

        with patch(
            "core.result_evidence.timezone.now", return_value=timezone.now() + timedelta(hours=2)
        ):
            with self.assertRaises(ValidationError):
                self.record()
        self.assertEqual(
            CandidateEvidence.objects.get().earliest_delete_at, evidence.earliest_delete_at
        )
        self.unchanged()


@skipUnless(connection.vendor == "postgresql", "Candidate event races require PostgreSQL")
@override_settings(SAAS_RESULT_VERIFIERS=VERIFIERS)
class ConcurrentCandidateEventTests(EventFixture, TransactionTestCase):
    def race(self, payloads):
        barrier = Barrier(2)

        def run(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                _, created = record_candidate_review(
                    User.objects.get(pk=self.user.id),
                    self.workspace.id,
                    self.operation.id,
                    *payload,
                )
                return "created" if created else "replayed"
            except IdempotencyConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, payloads))

    def test_duplicate_race_records_one_event(self):
        payload = self.signed()
        self.assertCountEqual(self.race([payload, payload]), ["created", "replayed"])
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.unchanged()

    def test_conflicting_race_cannot_replace_or_accept_results(self):
        changed = deepcopy(self.data)
        changed["event_ref"] = "conflict-event"
        self.assertCountEqual(
            self.race([self.signed(), self.signed(changed)]), ["created", "conflict"]
        )
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.unchanged()

    def test_cross_workspace_event_collision_commits_one_global_source_event(self):
        workspace, operation, data = self.other_operation()
        barrier = Barrier(2)

        def run(item):
            workspace_id, operation_id, payload = item
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                record_candidate_review(
                    User.objects.get(pk=self.user.id), workspace_id, operation_id, *payload
                )
                return "created"
            except IdempotencyConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    run,
                    [
                        (self.workspace.id, self.operation.id, self.signed()),
                        (workspace.id, operation.id, self.signed(data)),
                    ],
                )
            )
        self.assertCountEqual(results, ["created", "conflict"])
        self.assertEqual(CandidateEvidence.objects.count(), 1)
        self.unchanged()
