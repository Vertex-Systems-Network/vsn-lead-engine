"""Shared pure record eligibility checks; never signature or acceptance authority."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

RECORD = {
    "record_ref",
    "country",
    "category",
    "observed_at",
    "fields",
    "field_lineage",
    "purpose",
    "retention_version",
}
RIGHTS = {
    "version",
    "purpose",
    "retention_version",
    "max_age_seconds",
    "display_fields",
    "storage_fields",
    "display_allowed",
    "storage_allowed",
}
ALLOWED_FIELDS = {"business_name", "phone", "city", "website", "status", "address"}


@dataclass(frozen=True, slots=True)
class CandidateReview:
    """Redacted comparison evidence, explicitly not an accepted-result receipt.

    Equal bytes have equal digests; durable event collision/replay and R2 dedupe
    remain future ingestion gates. Never use this count to settle usage.
    """

    event_ref: str
    body_hash: str
    candidate_count: int
    earliest_delete_at: datetime


def token(value, limit=96):
    return isinstance(value, str) and re.fullmatch(rf"[A-Za-z0-9._:-]{{1,{limit}}}", value)


def instant(value):
    if type(value) is not int:
        raise ValueError()
    return datetime.fromtimestamp(value, UTC)


def checked_candidate_records(body, data, policy, search, now, issued):
    rights = policy.controls.get("result_contract")
    if not isinstance(rights, dict) or set(rights) != RIGHTS:
        raise ValueError()
    if type(rights["version"]) is not int or rights["version"] != 1:
        raise ValueError()
    if rights["display_allowed"] is not True or rights["storage_allowed"] is not True:
        raise ValueError()
    if not token(rights["purpose"], 64) or not token(rights["retention_version"], 64):
        raise ValueError()
    age = rights["max_age_seconds"]
    if type(age) is not int or not 1 <= age <= 2592000:
        raise ValueError()
    for key in ("display_fields", "storage_fields"):
        values = rights[key]
        if (
            not isinstance(values, list)
            or not values
            or any(type(x) is not str for x in values)
            or len(values) != len(set(values))
            or not set(values) <= ALLOWED_FIELDS
        ):
            raise ValueError()
    rows = data["records"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= min(25, search["result_limit"]):
        raise ValueError()
    refs = set()
    deadlines = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != RECORD or not token(row["record_ref"]):
            raise ValueError()
        if row["record_ref"] in refs:
            raise ValueError()
        refs.add(row["record_ref"])
        if (
            row["country"] not in {"US", "CA"}
            or row["country"] not in search["countries"]
            or row["category"] not in search["categories"]
        ):
            raise ValueError()
        if (
            row["purpose"] != rights["purpose"]
            or row["retention_version"] != rights["retention_version"]
        ):
            raise ValueError()
        observed = instant(row["observed_at"])
        if (
            observed > min(issued, now) + timedelta(minutes=5)
            or observed + timedelta(seconds=age) <= now
        ):
            raise ValueError()
        fields = row["fields"]
        if (
            not isinstance(fields, dict)
            or not {"business_name", "phone"} <= set(fields)
            or not set(fields) <= ALLOWED_FIELDS
        ):
            raise ValueError()
        required = {
            "business_name" if field == "name" else field for field in search["required_fields"]
        }
        if not required <= set(fields):
            raise ValueError()
        if not set(fields) <= set(rights["display_fields"]) & set(rights["storage_fields"]):
            raise ValueError()
        if any(
            not isinstance(v, str)
            or not v.strip()
            or len(v) > 2000
            or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for v in fields.values()
        ):
            raise ValueError()
        # Conservative normalized NANP syntax. Not reachability/geographic proof.
        if not re.fullmatch(r"\+1[2-9][0-9]{2}[2-9][0-9]{6}", fields["phone"]):
            raise ValueError()
        if search["statuses"] and fields.get("status") not in search["statuses"]:
            raise ValueError()
        lineage = row["field_lineage"]
        if (
            not isinstance(lineage, dict)
            or set(lineage) != set(fields)
            or any(v != row["record_ref"] for v in lineage.values())
        ):
            raise ValueError()
        deadlines.append(observed + timedelta(seconds=age))
    return CandidateReview(
        data["event_ref"], hashlib.sha256(body).hexdigest(), len(rows), min(deadlines)
    )
