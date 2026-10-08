"""Current-rights tenant result snapshots. No export, ingestion or cleanup route."""

import json

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .job_history import locked_workspace
from .jobs import eligible_sources
from .models import AcceptedResult, Job, ResultAcceptance, SourcePolicy
from .result_evidence import ALLOWED_FIELDS, RIGHTS, token


@transaction.atomic
def results_snapshot(user, workspace_id, job_id):
    locked_workspace(user, workspace_id)
    job = Job.objects.filter(pk=job_id, workspace_id=workspace_id).first()
    if job is None:
        raise Http404("Workspace resource not found.")
    output = {
        "workspace_id": str(workspace_id),
        "job_id": str(job_id),
        "results": [],
        "withheld_count": min(job.result_count, 25),
    }
    acceptance = (
        ResultAcceptance.objects.select_related("operation")
        .filter(operation__job=job, operation__workspace_id=workspace_id)
        .first()
    )
    if acceptance is None:
        return output
    operation = acceptance.operation
    if (
        job.status != "completed"
        or job.result_count != acceptance.accepted_count
        or operation.status != "success"
    ):
        return output
    try:
        snapshot, _ = eligible_sources(job.search)
    except (PermissionDenied, ValidationError):
        return output
    if snapshot.get(operation.source_code) != {
        "version": operation.policy_version,
        "hash": operation.policy_fingerprint,
    }:
        return output
    policy = SourcePolicy.objects.get(pk=operation.source_code)
    rights = policy.controls.get("result_contract")
    if (
        not isinstance(rights, dict)
        or set(rights) != RIGHTS
        or rights.get("display_allowed") is not True
        or rights.get("storage_allowed") is not True
        or not token(rights.get("purpose"), 64)
        or not token(rights.get("retention_version"), 64)
    ):
        return output
    for key in ("display_fields", "storage_fields"):
        values = rights.get(key)
        if (
            not isinstance(values, list)
            or not values
            or any(type(x) is not str for x in values)
            or not set(values) <= ALLOWED_FIELDS
        ):
            return output
    rows = list(
        AcceptedResult.objects.filter(
            workspace_id=workspace_id, job=job, acceptance=acceptance
        ).order_by("id")[:26]
    )
    if len(rows) != acceptance.accepted_count or len(rows) > 25:
        return output
    now = timezone.now()
    for row in rows:
        fields = row.fields
        if (
            row.delete_at <= now
            or row.purpose != rights["purpose"]
            or row.retention_version != rights["retention_version"]
            or row.country not in job.search["countries"]
            or row.category not in job.search["categories"]
        ):
            continue
        if (
            not isinstance(fields, dict)
            or not {"business_name", "phone"} <= set(fields)
            or not set(fields)
            <= set(rights["display_fields"]) & set(rights["storage_fields"]) & ALLOWED_FIELDS
        ):
            continue
        if any(
            not isinstance(v, str)
            or not v.strip()
            or len(v) > 2000
            or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for v in fields.values()
        ):
            continue
        if (
            not isinstance(row.field_lineage, dict)
            or set(row.field_lineage) != set(fields)
            or any(v != row.record_ref for v in row.field_lineage.values())
        ):
            continue
        # Raw source record references and signing/dedupe identities stay internal.
        entry = {
            "id": str(row.id),
            "country": row.country,
            "category": row.category,
            "fields": fields,
            "source_code": operation.source_code,
            "policy_version": operation.policy_version,
            "observed_at": row.observed_at.isoformat(),
            "delete_at": row.delete_at.isoformat(),
            "retention_version": row.retention_version,
            "provenance_fields": sorted(fields),
        }
        if len(json.dumps(entry, ensure_ascii=True, separators=(",", ":")).encode()) > 3072:
            continue
        output["results"].append(entry)
    output["withheld_count"] = acceptance.accepted_count - len(output["results"])
    return output
