"""Disabled v3 intake keeps exact proof, tenant dedupe and reservation boundaries."""

import hashlib
import hmac
import json
from copy import deepcopy
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import test_batch_manifest as manifests
from .batch_allocation import allocate_result_batch
from .batch_events import record_batch_candidates
from .batch_intake import accept_result_batch
from .models import (
    AcceptedFingerprint,
    AcceptedResult,
    BatchAcceptance,
    DispatchOperation,
    UsageReservation,
)
from .services import IdempotencyConflict
from .test_batch_events import KEY, SETTINGS, fixture


class IntakeFixture:
    def setUp(self):
        self.user, self.operation, self.batch, self.candidate = fixture()
        self.namespace = f"saas-results/v1/{self.operation.workspace_id}"
        self.dedupe_settings = override_settings(
            SAAS_BATCH_DEDUPE_VERIFIERS={self.namespace: {"dedupe": manifests.DEDUPE}}
        )
        self.dedupe_settings.enable()
        self.addCleanup(self.dedupe_settings.disable)
        self.candidate_body = json.dumps(self.candidate, sort_keys=True).encode()
        self.candidate_signature = hmac.new(KEY, self.candidate_body, hashlib.sha256).hexdigest()
        record_batch_candidates(
            self.user,
            self.operation.workspace_id,
            self.batch.pk,
            self.candidate_body,
            self.candidate_signature,
        )

    def manifest(self):
        data = {
            key: self.candidate[key]
            for key in (
                "workspace_id",
                "job_id",
                "operation_id",
                "batch_id",
                "provider_key",
                "source_code",
                "request_hash",
                "policy_fingerprint",
            )
        }
        data.update(
            version=3,
            kind="accepted-batch",
            source_key_id="source",
            dedupe_key_id="dedupe",
            receipt_ref="receipt-1",
            issued_at=self.candidate["issued_at"],
            provider_calls=1,
            registry_namespace=self.namespace,
            registry_contract="r2-exact-objects-v1",
            qualification_contract="vsn-phone-usca-v1",
            registry_state="committed",
            candidate_body_hash=hashlib.sha256(self.candidate_body).hexdigest(),
            candidate_event_ref=self.candidate["event_ref"],
            records=[
                {
                    "record_ref": "record-1",
                    "tokens": ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24],
                }
            ],
        )
        return data

    def intake(self, data=None):
        body = json.dumps(self.manifest() if data is None else data).encode()
        return accept_result_batch(
            self.user,
            self.operation.workspace_id,
            self.batch.pk,
            self.candidate_body,
            self.candidate_signature,
            body,
            hmac.new(manifests.SOURCE, body, hashlib.sha256).hexdigest(),
            hmac.new(manifests.DEDUPE, body, hashlib.sha256).hexdigest(),
        )


@override_settings(
    **SETTINGS,
    SAAS_BATCH_ACCEPTANCE_ENABLED=True,
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
)
class BatchIntakeTests(IntakeFixture, TestCase):
    def test_default_gate_and_exact_replay_preserve_original_reservation(self):
        with override_settings(SAAS_BATCH_ACCEPTANCE_ENABLED=False):
            with self.assertRaises(PermissionDenied):
                self.intake()
        first, created = self.intake()
        second, replay = self.intake()
        self.assertTrue(created)
        self.assertFalse(replay)
        self.assertEqual(first.pk, second.pk)
        row = AcceptedResult.objects.get(batch_acceptance=first)
        self.assertEqual(row.batch_position, 1)
        self.assertEqual(row.field_lineage, self.candidate["records"][0]["field_lineage"])
        self.assertEqual(AcceptedFingerprint.objects.filter(result=row).count(), 3)
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(reservation.status, "reserved")
        self.operation.job.refresh_from_db()
        self.assertEqual(
            (self.operation.job.status, self.operation.job.result_count), ("running", 0)
        )

    def test_changed_exact_body_and_reference_reuse_cannot_write(self):
        self.intake()
        changed = deepcopy(self.manifest())
        changed["receipt_ref"] = "receipt-2"
        with self.assertRaises(IdempotencyConflict):
            self.intake(changed)
        self.assertEqual((BatchAcceptance.objects.count(), AcceptedResult.objects.count()), (1, 1))

    def test_revoked_rights_or_key_reject_even_exact_replay(self):
        self.intake()
        with override_settings(SAAS_BATCH_VERIFIERS={}):
            with self.assertRaises(ValidationError):
                self.intake()

    def test_unknown_effect_replays_only_recorded_acceptance(self):
        first, _ = self.intake()
        DispatchOperation.objects.filter(pk=self.operation.pk).update(
            status="unknown", unknown_at=timezone.now()
        )
        same, created = self.intake()
        self.assertFalse(created)
        self.assertEqual(same.pk, first.pk)
        changed = self.manifest()
        changed["receipt_ref"] = "different"
        with self.assertRaises(IdempotencyConflict):
            self.intake(changed)

    def test_insert_failure_rolls_back_acceptance_payload_and_tokens(self):
        with patch(
            "core.batch_intake.AcceptedFingerprint.objects.bulk_create",
            side_effect=IntegrityError("injected"),
        ):
            with self.assertRaises(IdempotencyConflict):
                self.intake()
        self.assertFalse(BatchAcceptance.objects.exists())
        self.assertFalse(AcceptedResult.objects.exists())
        self.assertFalse(AcceptedFingerprint.objects.exists())
        reservation = UsageReservation.objects.get(pk=self.operation.outbox.reservation_id)
        self.assertEqual(reservation.status, "reserved")

    def second_batch(self):
        batch, _ = allocate_result_batch(
            self.user, self.operation.workspace_id, self.operation.pk, 2
        )
        self.batch = batch
        self.candidate = deepcopy(self.candidate)
        self.candidate["batch_id"] = str(batch.pk)
        self.candidate["event_ref"] = "event-2"
        self.candidate["records"][0]["record_ref"] = "record-2"
        self.candidate["records"][0]["field_lineage"] = {
            key: "record-2" for key in self.candidate["records"][0]["fields"]
        }
        self.candidate_body = json.dumps(self.candidate, sort_keys=True).encode()
        self.candidate_signature = hmac.new(KEY, self.candidate_body, hashlib.sha256).hexdigest()
        record_batch_candidates(
            self.user,
            self.operation.workspace_id,
            batch.pk,
            self.candidate_body,
            self.candidate_signature,
        )

    def test_original_call_budget_and_shared_fingerprint_uniqueness(self):
        self.intake()
        self.second_batch()
        second = self.manifest()
        second["receipt_ref"] = "receipt-2"
        second["records"][0]["record_ref"] = "record-2"
        second["provider_calls"] = 2
        with self.assertRaises(ValidationError):
            self.intake(second)
        second["provider_calls"] = 1
        with self.assertRaises(IdempotencyConflict):
            self.intake(second)
        self.assertEqual(BatchAcceptance.objects.count(), 1)
        self.assertEqual(AcceptedResult.objects.count(), 1)
