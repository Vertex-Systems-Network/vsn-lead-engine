import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from . import test_batch_candidates as candidates
from . import test_batch_manifest as manifests
from .batch_payload import verified_batch_payload


@override_settings(
    SAAS_BATCH_CANDIDATE_VERIFIERS={"fixture": {"candidate": candidates.KEY}},
    SAAS_BATCH_VERIFIERS={"fixture": {"source": manifests.SOURCE}},
    SAAS_BATCH_DEDUPE_VERIFIERS={"isolated/test": {"dedupe": manifests.DEDUPE}},
)
class PairedPayloadTests(SimpleTestCase):
    def setUp(self):
        candidates.BatchCandidateTests.setUp(self)

    def accepted_data(self, body):
        data = {
            name: str(getattr(self.binding, name))
            for name in (
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
            issued_at=self.data["issued_at"],
            provider_calls=1,
            registry_namespace="isolated/test",
            registry_contract="r2-exact-objects-v1",
            qualification_contract="vsn-phone-usca-v1",
            registry_state="committed",
            candidate_body_hash=hashlib.sha256(body).hexdigest(),
            candidate_event_ref=self.data["event_ref"],
            records=[
                {
                    "record_ref": "record-1",
                    "tokens": ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24],
                }
            ],
        )
        return data

    def pair(self, changes=None, dedupe_key=manifests.DEDUPE, candidate_signature=None):
        candidate = json.dumps(self.data).encode()
        data = self.accepted_data(candidate)
        data.update(changes or {})
        body = json.dumps(data).encode()
        return verified_batch_payload(
            candidate,
            candidate_signature or hmac.new(candidates.KEY, candidate, hashlib.sha256).hexdigest(),
            body,
            hmac.new(manifests.SOURCE, body, hashlib.sha256).hexdigest(),
            hmac.new(dedupe_key, body, hashlib.sha256).hexdigest(),
            self.binding,
            "isolated/test",
            2,
            self.policy,
            self.search,
        )

    def denied(self, **kwargs):
        with self.assertRaises(ValidationError):
            self.pair(**kwargs)

    def test_immutable_exact_rows_have_no_database_or_storage_side_effect(self):
        review, manifest, rows = self.pair()
        self.assertEqual((review.candidate_count, manifest.accepted_count, len(rows)), (1, 1, 1))
        self.assertEqual(dict(rows[0].fields), self.data["records"][0]["fields"])
        self.assertEqual(int((rows[0].delete_at - rows[0].observed_at).total_seconds()), 3600)
        self.assertNotIn("Fixture only", repr(rows))
        self.assertNotIn("record-1", repr(rows))
        with self.assertRaises(FrozenInstanceError):
            rows[0].country = "CA"
        self.data["records"][0]["fields"]["business_name"] = "Changed input"
        self.assertEqual(dict(rows[0].fields)["business_name"], "Fixture only")

    def test_signed_reference_set_or_candidate_digest_mismatch_is_denied(self):
        self.denied(
            changes={
                "records": [
                    {
                        "record_ref": "different",
                        "tokens": ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24],
                    }
                ]
            }
        )
        self.denied(changes={"candidate_body_hash": "f" * 64})
        self.denied(changes={"candidate_event_ref": "different"})

    def test_signed_count_mismatch_is_denied(self):
        other = deepcopy(self.row)
        other["record_ref"] = "record-2"
        other["field_lineage"] = {key: "record-2" for key in other["fields"]}
        self.data["records"].append(other)
        self.denied()

    def test_dedupe_authority_cannot_reuse_candidate_key(self):
        with override_settings(
            SAAS_BATCH_DEDUPE_VERIFIERS={"isolated/test": {"dedupe": candidates.KEY}}
        ):
            self.denied(dedupe_key=candidates.KEY)

    def test_acceptance_cannot_predate_candidate_issuance_window(self):
        self.denied(changes={"issued_at": self.data["issued_at"] - 301})
        self.assertEqual(
            self.pair(changes={"issued_at": self.data["issued_at"] - 300})[1].accepted_count, 1
        )

    def test_domain_fingerprint_is_required_exactly_when_website_exists(self):
        tokens = ["n:" + "1" * 24, "l:" + "2" * 24, "s:" + "3" * 24, "d:" + "4" * 24]
        row = {"record_ref": "record-1", "tokens": tokens}
        self.denied(changes={"records": [row]})
        for grant in ("storage_fields", "display_fields"):
            self.policy.controls["result_contract"][grant].append("website")
        self.data["records"][0]["fields"]["website"] = "https://fixture.invalid"
        self.data["records"][0]["field_lineage"]["website"] = "record-1"
        self.denied()
        self.assertEqual(self.pair(changes={"records": [row]})[2][0].tokens, tuple(tokens))
        self.denied(
            changes={"records": [{"record_ref": "record-1", "tokens": tokens + ["d:" + "5" * 24]}]}
        )

    def test_current_rights_signature_and_phone_qualification_still_apply(self):
        self.denied(candidate_signature="0" * 64)
        self.data["records"][0]["fields"]["phone"] = "unqualified"
        self.denied()
        self.data["records"][0]["fields"]["phone"] = "+12025550123"
        self.policy.controls["result_contract"]["storage_allowed"] = False
        self.denied()

    def test_twenty_five_rows_map_by_ref_without_receipt_order_or_larger_batch(self):
        rows, proofs = [], []
        for index in range(25):
            row = deepcopy(self.row)
            row["record_ref"] = f"record-{index}"
            row["field_lineage"] = {key: row["record_ref"] for key in row["fields"]}
            rows.append(row)
            proofs.append(
                {
                    "record_ref": row["record_ref"],
                    "tokens": [f"{prefix}:{index:024x}" for prefix in ("n", "l", "s")],
                }
            )
        self.data["records"] = rows
        checked = self.pair(changes={"records": list(reversed(proofs))})[2]
        self.assertEqual([r.record_ref for r in checked], [r["record_ref"] for r in rows])
        self.assertEqual([r.tokens for r in checked], [tuple(r["tokens"]) for r in proofs])
        self.data["records"].append({**rows[-1], "record_ref": "record-26"})
        self.denied(changes={"records": proofs})
