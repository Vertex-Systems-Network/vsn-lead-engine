import hashlib
import hmac
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import IntegrityError, close_old_connections, connection
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_result_evidence as fixtures
from .accepted_results import accept_results
from .attempts import claim_pre_dispatch
from .candidate_events import record_candidate_review
from .dispatch import begin_dispatch
from .jobs import RevisionConflict, enqueue_job
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    CandidateEvidence,
    Entitlement,
    JobOutbox,
    Membership,
    ResultAcceptance,
    SourcePolicy,
    UsageCounter,
    User,
)
from .receipts import reconcile_receipt
from .services import IdempotencyConflict, create_draft, create_workspace
from .test_receipts import VERIFIERS, proof

SOURCE_KEY = b"synthetic-source-acceptance-key-0000000000"
DEDUPE_KEY = b"synthetic-isolated-registry-key-1111111111"


def signed_data(data, key):
    body = json.dumps(data, sort_keys=True).encode()
    return body, hmac.new(key, body, hashlib.sha256).hexdigest()


class AcceptanceFixture:
    def setUp(self):
        fixtures.CandidateEvidenceTests.setUp(self)
        self.namespace = f"saas-results/v1/{self.workspace.id}"
        self.settings_override = override_settings(
            SAAS_RESULT_VERIFIERS=VERIFIERS,
            SAAS_ACCEPTANCE_VERIFIERS={"fixture": {"source-test": SOURCE_KEY}},
            SAAS_DEDUPE_VERIFIERS={self.namespace: {"registry-test": DEDUPE_KEY}},
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.candidate, _ = record_candidate_review(
            self.user, self.workspace.id, self.operation.id, *self.candidate_signed()
        )
        self.acceptance_data = {
            "version": 2,
            "kind": "accepted-results",
            "key_id": "source-test",
            "dedupe_key_id": "registry-test",
            "receipt_ref": "acceptance-test-1",
            "workspace_id": str(self.workspace.id),
            "job_id": str(self.job.id),
            "operation_id": str(self.operation.id),
            "provider_key": str(self.operation.provider_key),
            "request_hash": self.job.request_hash,
            "policy_fingerprint": self.operation.policy_fingerprint,
            "source_code": "fixture",
            "candidate_event_ref": self.candidate.event_ref,
            "candidate_body_hash": self.candidate.body_hash,
            "registry_namespace": self.namespace,
            "registry_contract": "r2-exact-objects-v1",
            "qualification_contract": "vsn-phone-usca-v1",
            "registry_state": "committed",
            "issued_at": int(timezone.now().timestamp()),
            "provider_calls": 1,
            "records": [
                {
                    "record_ref": "synthetic-record-1",
                    "tokens": ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24],
                }
            ],
        }

    def candidate_signed(self, data=None):
        return fixtures.CandidateEvidenceTests.signed(self, data)

    def receipt_signed(self, data=None):
        body, source_signature = signed_data(
            self.acceptance_data if data is None else data, SOURCE_KEY
        )
        return body, source_signature, hmac.new(DEDUPE_KEY, body, hashlib.sha256).hexdigest()

    def accept(self, data=None):
        return accept_results(
            self.user,
            self.workspace.id,
            self.operation.id,
            *self.candidate_signed(),
            *self.receipt_signed(data),
        )

    def no_acceptance(self):
        fixtures.CandidateEvidenceTests.unchanged(self)
        self.assertFalse(AcceptedResult.objects.exists())
        self.assertFalse(ResultAcceptance.objects.exists())
        self.assertFalse(AcceptedFingerprint.objects.exists())


class AcceptedResultTests(AcceptanceFixture, TestCase):
    def test_multisource_outbox_and_expired_candidates_are_denied(self):
        from datetime import timedelta

        JobOutbox.objects.filter(pk=self.intent.pk).update(
            source_snapshot={
                **self.intent.source_snapshot,
                "other": {"version": 1, "hash": "0" * 64},
            }
        )
        with self.assertRaises(RevisionConflict):
            self.accept()
        JobOutbox.objects.filter(pk=self.intent.pk).update(
            source_snapshot=self.intent.source_snapshot
        )
        with patch(
            "core.accepted_results.timezone.now", return_value=timezone.now() + timedelta(hours=2)
        ):
            with self.assertRaises(ValidationError):
                self.accept()
        self.no_acceptance()

    def test_name_and_address_search_fields_map_to_candidate_payload(self):
        from .result_evidence import checked_candidates

        policy = SourcePolicy.objects.get(pk="fixture")
        policy.controls["result_contract"]["display_fields"].append("address")
        policy.controls["result_contract"]["storage_fields"].append("address")
        data = deepcopy(self.data)
        row = data["records"][0]
        row["fields"]["address"] = "Synthetic address"
        row["field_lineage"]["address"] = row["record_ref"]
        search = {**self.job.search, "required_fields": ["name", "address", "phone"]}
        review = checked_candidates(
            *self.candidate_signed(data), self.operation, policy, search, timezone.now()
        )
        self.assertEqual(review.candidate_count, 1)

    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_deep_v1_receipt_fails_closed_without_changing_result_accounting(self):
        body = b"[" * 1500 + b"0" + b"]" * 1500
        with self.assertRaises(ValidationError):
            reconcile_receipt(
                self.user,
                self.workspace.id,
                self.operation.id,
                body,
                hmac.new(fixtures.KEY, body, hashlib.sha256).hexdigest(),
            )
        self.no_acceptance()

    def test_atomic_store_actual_usage_and_identical_replay(self):
        receipt, created = self.accept()
        replay, repeated = self.accept()
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(receipt.pk, replay.pk)
        self.assertEqual(AcceptedResult.objects.count(), 1)
        self.assertEqual(AcceptedFingerprint.objects.count(), 3)
        result = AcceptedResult.objects.get()
        self.assertEqual(
            (result.workspace_id, result.job_id, result.acceptance_id),
            (self.workspace.id, self.job.id, receipt.id),
        )
        self.assertEqual(result.fields, self.data["records"][0]["fields"])
        self.assertEqual(result.field_lineage, self.data["records"][0]["field_lineage"])
        self.assertEqual(result.delete_at, self.candidate.earliest_delete_at)
        self.job.refresh_from_db()
        self.intent.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(
            (self.job.status, self.job.result_count, self.job.revision, self.intent.status),
            ("completed", 1, 3, "done"),
        )
        self.assertEqual(
            self.intent.reservation.settlement,
            {"leads": 1, "jobs": 1, "provider_calls": 1, "exports": 0},
        )
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertEqual(
            (counter.leads, counter.jobs, counter.provider_calls, counter.exports), (1, 1, 1, 0)
        )

    def test_changed_signed_replay_conflicts_without_double_charge(self):
        self.accept()
        data = deepcopy(self.acceptance_data)
        data["receipt_ref"] = "changed"
        with self.assertRaises(IdempotencyConflict):
            self.accept(data)
        self.assertEqual(ResultAcceptance.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)

    def test_empty_registries_and_shared_dedupe_keys_cannot_mint_results(self):
        for change in [
            {"SAAS_ACCEPTANCE_VERIFIERS": {}},
            {"SAAS_DEDUPE_VERIFIERS": {}},
            {"SAAS_RESULT_VERIFIERS": {}},
            {"SAAS_DEDUPE_VERIFIERS": {self.namespace: {"registry-test": SOURCE_KEY}}},
            {"SAAS_DEDUPE_VERIFIERS": {self.namespace: {"registry-test": fixtures.KEY}}},
        ]:
            with override_settings(**change), self.assertRaises(ValidationError):
                self.accept()
        self.no_acceptance()

    def test_unsigned_changed_bytes_and_production_namespace_are_rejected(self):
        body, source, dedupe = self.receipt_signed()
        for b, s, d in [
            (body, "0" * 64, dedupe),
            (body, source, "0" * 64),
            (body + b" ", source, dedupe),
            (b"x" * 16385, source, dedupe),
        ]:
            with self.assertRaises(ValidationError):
                accept_results(
                    self.user,
                    self.workspace.id,
                    self.operation.id,
                    *self.candidate_signed(),
                    b,
                    s,
                    d,
                )
        data = deepcopy(self.acceptance_data)
        data["registry_namespace"] = "production-registry"
        with self.assertRaises(ValidationError):
            self.accept(data)
        self.no_acceptance()

    def test_identity_qualification_record_and_counter_claims_fail_closed(self):
        for key, value in {
            "version": 1,
            "kind": "other",
            "workspace_id": str(self.job.id),
            "job_id": str(self.workspace.id),
            "candidate_event_ref": "other",
            "candidate_body_hash": "0" * 64,
            "registry_state": "pending",
            "registry_contract": "bloom-filter",
            "qualification_contract": "unknown",
            "provider_calls": True,
            "issued_at": 0,
            "accepted_count": 100,
            "records": [],
            "source_code": "other",
            "provider_key": str(self.intent.id),
        }.items():
            with self.subTest(key=key):
                data = deepcopy(self.acceptance_data)
                data[key] = value
                with self.assertRaises(ValidationError):
                    self.accept(data)
        self.no_acceptance()

    def test_fingerprint_contract_and_record_binding_are_bounded(self):
        for records in [
            [{"record_ref": "other", "tokens": self.acceptance_data["records"][0]["tokens"]}],
            [{"record_ref": "synthetic-record-1", "tokens": ["n:" + "1" * 24]}],
            [{"record_ref": "synthetic-record-1", "tokens": ["n:" + "1" * 24] * 3}],
            [
                {
                    "record_ref": "synthetic-record-1",
                    "tokens": ["raw-phone", "raw-name", "raw-record"],
                }
            ],
        ]:
            data = deepcopy(self.acceptance_data)
            data["records"] = records
            with self.assertRaises(ValidationError):
                self.accept(data)
        self.no_acceptance()

    def test_candidate_payload_must_match_recorded_evidence(self):
        changed = deepcopy(self.data)
        changed["records"][0]["fields"]["business_name"] = "Changed"
        with self.assertRaises(ValidationError):
            accept_results(
                self.user,
                self.workspace.id,
                self.operation.id,
                *self.candidate_signed(changed),
                *self.receipt_signed(),
            )
        CandidateEvidence.objects.filter(pk=self.candidate.pk).delete()
        with self.assertRaises(ValidationError):
            self.accept()
        self.no_acceptance()

    def test_live_membership_entitlement_and_policy_still_gate_replay(self):
        self.accept()
        membership = Membership.objects.get(workspace=self.workspace, user=self.user)
        for role in ["member", "viewer"]:
            membership.role = role
            membership.save()
            with self.assertRaises(PermissionDenied):
                self.accept()
        membership.role = "owner"
        membership.save()
        SourcePolicy.objects.filter(pk="fixture").update(enabled=False)
        with self.assertRaises(PermissionDenied):
            self.accept()
        SourcePolicy.objects.filter(pk="fixture").update(enabled=True)
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.accept()
        membership.delete()
        with self.assertRaises(Http404):
            self.accept()
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)

    def test_foreign_workspace_and_current_lowered_caps_do_not_store(self):
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(Http404):
            accept_results(
                self.user,
                other.id,
                self.operation.id,
                *self.candidate_signed(),
                *self.receipt_signed(),
            )
        Entitlement.objects.filter(workspace=self.workspace).update(lead_limit=1)
        with self.assertRaises(PermissionDenied):
            self.accept()
        self.no_acceptance()

    def test_finalization_failure_rolls_back_payload_tokens_receipt_and_usage(self):
        with patch("core.accepted_results._settle_locked", side_effect=IntegrityError("injected")):
            with self.assertRaises(IdempotencyConflict):
                self.accept()
        self.no_acceptance()

    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_v1_terminal_and_v2_acceptance_cannot_both_finalize(self):
        self.accept()
        with self.assertRaises(RevisionConflict):
            reconcile_receipt(
                self.user, self.workspace.id, self.operation.id, *proof(self.operation)
            )
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)

    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_already_v1_completed_job_cannot_gain_accepted_results(self):
        reconcile_receipt(self.user, self.workspace.id, self.operation.id, *proof(self.operation))
        with self.assertRaises(RevisionConflict):
            self.accept()
        self.assertFalse(AcceptedResult.objects.exists())
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 0)

    def test_duplicate_across_later_job_is_not_new_accepted_use(self):
        self.accept()
        job, _ = create_draft(self.user, self.workspace.id, self.job.search, "later-job")
        enqueue_job(self.user, self.workspace.id, job.id, 0)
        intent = JobOutbox.objects.get(job=job)
        lease = claim_pre_dispatch(intent.id)
        operation = begin_dispatch(intent.id, lease.token)[0]
        candidate_data = deepcopy(self.data)
        candidate_data.update(
            job_id=str(job.id),
            operation_id=str(operation.id),
            provider_key=str(operation.provider_key),
            request_hash=job.request_hash,
            policy_fingerprint=operation.policy_fingerprint,
            event_ref="later-candidate",
        )
        candidate_body, candidate_sig = self.candidate_signed(candidate_data)
        candidate, _ = record_candidate_review(
            self.user, self.workspace.id, operation.id, candidate_body, candidate_sig
        )
        receipt_data = deepcopy(self.acceptance_data)
        receipt_data.update(
            job_id=str(job.id),
            operation_id=str(operation.id),
            provider_key=str(operation.provider_key),
            request_hash=job.request_hash,
            policy_fingerprint=operation.policy_fingerprint,
            candidate_event_ref=candidate.event_ref,
            candidate_body_hash=candidate.body_hash,
            receipt_ref="later-receipt",
        )
        with self.assertRaises(IdempotencyConflict):
            accept_results(
                self.user,
                self.workspace.id,
                operation.id,
                candidate_body,
                candidate_sig,
                *self.receipt_signed(receipt_data),
            )
        self.assertEqual(AcceptedResult.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)
        intent.reservation.refresh_from_db()
        self.assertEqual(intent.reservation.status, "reserved")

    def test_populated_migration_reverse_guard(self):
        guard = importlib.import_module(
            "core.migrations.0013_accepted_results"
        ).protect_results_rollback
        guard(apps, connection.schema_editor(atomic=False))
        self.accept()
        with self.assertRaises(RuntimeError):
            guard(apps, connection.schema_editor(atomic=False))
        self.assertEqual(AcceptedResult.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "Accepted-result races require PostgreSQL")
class ConcurrentAcceptedResultTests(AcceptanceFixture, TransactionTestCase):
    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_v1_and_v2_race_commit_one_terminal_contract(self):
        candidate = self.candidate_signed()
        receipt = self.receipt_signed()
        barrier = Barrier(2)

        def run(version):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                user = User.objects.get(pk=self.user.id)
                if version == 1:
                    reconcile_receipt(
                        user, self.workspace.id, self.operation.id, *proof(self.operation)
                    )
                else:
                    accept_results(user, self.workspace.id, self.operation.id, *candidate, *receipt)
                return "committed"
            except RevisionConflict:
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [1, 2]))
        self.assertCountEqual(results, ["committed", "conflict"])
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertEqual((counter.jobs, counter.provider_calls), (1, 1))
        self.assertEqual(counter.leads, AcceptedResult.objects.count())

    def race(self, receipts):
        candidate = self.candidate_signed()
        barrier = Barrier(2)

        def run(receipt):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                _, created = accept_results(
                    User.objects.get(pk=self.user.id),
                    self.workspace.id,
                    self.operation.id,
                    *candidate,
                    *receipt,
                )
                return "created" if created else "replayed"
            except (IdempotencyConflict, RevisionConflict):
                return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, receipts))

    def test_duplicate_acceptance_charges_once(self):
        receipt = self.receipt_signed()
        self.assertCountEqual(self.race([receipt, receipt]), ["created", "replayed"])
        self.assertEqual(AcceptedResult.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)

    def test_conflicting_acceptance_cannot_replace_results_or_usage(self):
        changed = deepcopy(self.acceptance_data)
        changed["receipt_ref"] = "changed"
        self.assertCountEqual(
            self.race([self.receipt_signed(), self.receipt_signed(changed)]),
            ["created", "conflict"],
        )
        self.assertEqual(AcceptedResult.objects.count(), 1)
        self.assertEqual(UsageCounter.objects.get(workspace=self.workspace).leads, 1)
