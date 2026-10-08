import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from uuid import uuid4

from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .attempts import claim_pre_dispatch
from .dispatch import begin_dispatch
from .jobs import RevisionConflict, enqueue_job
from .models import DispatchReceipt, Entitlement, JobOutbox, Membership, SourcePolicy, UsageCounter
from .receipts import reconcile_receipt
from .result_evidence import review_candidates
from .services import create_workspace
from .test_jobs import fixture
from .test_receipts import KEY, VERIFIERS, proof

RIGHTS = {
    "version": 1,
    "purpose": "synthetic-test-only",
    "retention_version": "synthetic-v1",
    "max_age_seconds": 3600,
    "display_fields": ["business_name", "phone"],
    "storage_fields": ["business_name", "phone"],
    "display_allowed": True,
    "storage_allowed": True,
}


@override_settings(SAAS_RESULT_VERIFIERS=VERIFIERS)
class CandidateEvidenceTests(TestCase):
    def setUp(self):
        self.user, self.workspace, self.job = fixture()
        policy = SourcePolicy.objects.get(pk="fixture")
        policy.controls["result_contract"] = deepcopy(RIGHTS)
        policy.save()
        enqueue_job(self.user, self.workspace.id, self.job.id, 0)
        self.intent = JobOutbox.objects.get(job=self.job)
        lease = claim_pre_dispatch(self.intent.id)
        self.operation = begin_dispatch(self.intent.id, lease.token)[0]
        now = int(timezone.now().timestamp())
        self.data = {
            "version": 1,
            "key_id": "test",
            "event_ref": "synthetic-event-1",
            "operation_id": str(self.operation.id),
            "workspace_id": str(self.workspace.id),
            "job_id": str(self.job.id),
            "source_code": "fixture",
            "provider_key": str(self.operation.provider_key),
            "request_hash": self.job.request_hash,
            "policy_fingerprint": self.operation.policy_fingerprint,
            "issued_at": now,
            "records": [
                {
                    "record_ref": "synthetic-record-1",
                    "country": "US",
                    "category": "software",
                    "observed_at": now,
                    "fields": {"business_name": "Synthetic only", "phone": "+12025550123"},
                    "field_lineage": {
                        "business_name": "synthetic-record-1",
                        "phone": "synthetic-record-1",
                    },
                    "purpose": "synthetic-test-only",
                    "retention_version": "synthetic-v1",
                }
            ],
        }

    def signed(self, data=None):
        body = json.dumps(self.data if data is None else data, sort_keys=True).encode()
        return body, hmac.new(KEY, body, hashlib.sha256).hexdigest()

    def review(self, data=None):
        return review_candidates(
            self.user, self.workspace.id, self.operation.id, *self.signed(data)
        )

    def unchanged(self):
        self.job.refresh_from_db()
        self.operation.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual((self.job.status, self.job.result_count), ("running", 0))
        self.assertEqual(self.operation.status, "started")
        self.assertEqual(self.intent.reservation.status, "reserved")
        self.assertFalse(DispatchReceipt.objects.exists())
        counter = UsageCounter.objects.get(workspace=self.workspace)
        self.assertEqual(
            (counter.leads, counter.exports, counter.jobs, counter.provider_calls), (0, 0, 0, 0)
        )

    def test_redacted_repeatable_review_is_not_acceptance_or_accounting(self):
        first, second = self.review(), self.review()
        self.assertEqual(first, second)
        self.assertEqual(first.candidate_count, 1)
        self.assertNotIn("+12025550123", repr(first))
        self.assertNotIn("Synthetic only", repr(first))
        with self.assertRaises(FrozenInstanceError):
            first.candidate_count = 20
        self.unchanged()
        changed = deepcopy(self.data)
        changed["records"][0]["fields"]["business_name"] = "Changed candidate"
        self.assertNotEqual(first.body_hash, self.review(changed).body_hash)
        # A digest identifies conflict, but does not persist or resolve event reuse.
        self.unchanged()

    def test_unconfigured_unsigned_changed_bytes_and_separate_receipt_key_are_denied(self):
        body, signature = self.signed()
        with override_settings(SAAS_RESULT_VERIFIERS={}, SAAS_RECEIPT_VERIFIERS=VERIFIERS):
            with self.assertRaises(ValidationError):
                self.review()
        for b, sig in [
            (body, "0" * 64),
            (body + b" ", signature),
            (b"x" * 131073, signature),
            proof(self.operation),
        ]:
            with self.assertRaises(ValidationError):
                review_candidates(self.user, self.workspace.id, self.operation.id, b, sig)
        self.unchanged()

    def test_envelope_schema_identity_and_time_are_bound(self):
        for key, value in {
            "version": True,
            "key_id": "unknown",
            "event_ref": "unsafe/event",
            "operation_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "job_id": str(uuid4()),
            "source_code": "other",
            "provider_key": str(uuid4()),
            "request_hash": "0" * 64,
            "policy_fingerprint": "0" * 64,
            "issued_at": 0,
            "extra": "unsupported",
        }.items():
            with self.subTest(key=key):
                data = deepcopy(self.data)
                data[key] = value
                with self.assertRaises(ValidationError):
                    self.review(data)
        self.unchanged()

    def test_duplicate_json_empty_oversized_and_duplicate_records_are_denied(self):
        body, _ = self.signed()
        duplicate = b'{"version":1,' + body[1:]
        with self.assertRaises(ValidationError):
            review_candidates(
                self.user,
                self.workspace.id,
                self.operation.id,
                duplicate,
                hmac.new(KEY, duplicate, hashlib.sha256).hexdigest(),
            )
        for rows in [[], self.data["records"] * 2, self.data["records"] * 26]:
            data = deepcopy(self.data)
            data["records"] = rows
            with self.assertRaises(ValidationError):
                self.review(data)
        self.unchanged()

    def test_phone_scope_lineage_retention_and_fields_fail_closed(self):
        mutations = [
            ("country", "GB"),
            ("country", "CA"),
            ("category", "other"),
            ("observed_at", 0),
            ("observed_at", int(timezone.now().timestamp()) + 10000),
            ("observed_at", True),
            ("purpose", "other"),
            ("retention_version", "other"),
            ("fields", {"business_name": "Test"}),
            ("fields", {"business_name": "Test", "phone": "+440000000000"}),
            ("fields", {"business_name": "\nTest", "phone": "+12025550123"}),
            ("fields", {"business_name": "x" * 2001, "phone": "+12025550123"}),
            ("fields", {"business_name": "Test", "phone": "+12025550123", "email": "unsupported"}),
            ("field_lineage", {}),
            ("field_lineage", {"business_name": "other", "phone": "other"}),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                data = deepcopy(self.data)
                data["records"][0][key] = value
                with self.assertRaises(ValidationError):
                    self.review(data)
        self.unchanged()

    def test_live_policy_drift_and_kill_switch_invalidate_saved_evidence(self):
        for change in [{"enabled": False}, {"version": 2}, {"controls": {}}, {"countries": ["CA"]}]:
            with self.subTest(change=change):
                with self.captureOnCommitCallbacks():
                    policy = SourcePolicy.objects.get(pk="fixture")
                    previous = {k: getattr(policy, k) for k in change}
                    SourcePolicy.objects.filter(pk="fixture").update(**change)
                    with self.assertRaises((RevisionConflict, PermissionDenied)):
                        self.review()
                    SourcePolicy.objects.filter(pk="fixture").update(**previous)
        self.unchanged()

    def test_missing_unknown_or_denied_structured_rights_are_not_permissions(self):
        # A signed snapshot must still have an explicit structured contract.
        for value in [
            None,
            {},
            {**RIGHTS, "storage_allowed": False},
            {**RIGHTS, "display_allowed": "true"},
            {**RIGHTS, "max_age_seconds": True},
            {**RIGHTS, "storage_fields": ["phone"]},
            {**RIGHTS, "display_fields": ["phone", "unknown"]},
        ]:
            policy = SourcePolicy.objects.get(pk="fixture")
            policy.controls["result_contract"] = value
            policy.save()
            # Test parsing independently; service always rejects the changed snapshot first.
            from .result_evidence import checked_candidates

            with self.assertRaises(ValidationError):
                checked_candidates(
                    *self.signed(), self.operation, policy, self.job.search, timezone.now()
                )
        self.unchanged()

    def test_viewer_revoked_foreign_and_inactive_entitlement_are_denied(self):
        membership = Membership.objects.get(workspace=self.workspace, user=self.user)
        membership.role = "viewer"
        membership.save()
        with self.assertRaises(PermissionDenied):
            self.review()
        membership.role = "owner"
        membership.save()
        other = create_workspace(self.user, {"name": "Other", "timezone": "UTC"})
        with self.assertRaises(Http404):
            review_candidates(self.user, other.id, self.operation.id, *self.signed())
        Entitlement.objects.filter(workspace=self.workspace).update(active=False)
        with self.assertRaises(PermissionDenied):
            self.review()
        membership.delete()
        with self.assertRaises(Http404):
            self.review()
        self.unchanged()

    @override_settings(SAAS_RECEIPT_VERIFIERS=VERIFIERS)
    def test_terminal_receipt_never_becomes_nonzero_results_from_preflight(self):
        self.review()
        reconcile_receipt(self.user, self.workspace.id, self.operation.id, *proof(self.operation))
        with self.assertRaises(RevisionConflict):
            self.review()
        self.job.refresh_from_db()
        self.intent.reservation.refresh_from_db()
        self.assertEqual(self.job.result_count, 0)
        self.assertEqual(self.intent.reservation.settlement["leads"], 0)

    def test_deep_json_and_current_reservation_bounds_fail_closed(self):
        body = b"[" * 1500 + b"0" + b"]" * 1500
        with self.assertRaises(ValidationError):
            review_candidates(
                self.user,
                self.workspace.id,
                self.operation.id,
                body,
                hmac.new(KEY, body, hashlib.sha256).hexdigest(),
            )
        self.intent.reservation.leads = 0
        self.intent.reservation.save(update_fields=["leads"])
        with self.assertRaises(ValidationError):
            self.review()
        self.unchanged()
