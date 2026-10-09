"""Default-off bounded v3 pages; every continuation rechecks current rights."""

import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .batch_page_cursor import (
    PAGE_SIZE,
    PagePosition,
    decode_page_cursor,
    encode_page_cursor,
    require_page_signing_key,
)
from .job_history import locked_workspace
from .jobs import RevisionConflict, eligible_sources
from .models import (
    AcceptedResult,
    BatchAcceptance,
    BatchCandidateEvidence,
    DispatchOperation,
    Entitlement,
    Job,
    JobOutbox,
    ResultBatch,
    SourceBatchNoEffect,
    SourceBatchTerminal,
    SourcePolicy,
    UsageReservation,
)
from .result_evidence import ALLOWED_FIELDS, RIGHTS, token
from .result_query import filter_options, validate_filters


def _rights(policy):
    rights = policy.controls.get("result_contract")
    if (
        not isinstance(rights, dict)
        or set(rights) != RIGHTS
        or rights.get("display_allowed") is not True
        or rights.get("storage_allowed") is not True
        or not token(rights.get("purpose"), 64)
        or not token(rights.get("retention_version"), 64)
    ):
        raise PermissionDenied("Current source display rights are unavailable.")
    for key in ("display_fields", "storage_fields"):
        values = rights.get(key)
        if (
            not isinstance(values, list)
            or not values
            or any(type(x) is not str for x in values)
            or not set(values) <= ALLOWED_FIELDS
        ):
            raise PermissionDenied("Current source fields are unavailable.")
    return rights


def _position(row):
    batch = row.batch_acceptance.candidate.batch
    return PagePosition(batch.operation.source_code, batch.ordinal, row.batch_position, str(row.pk))


def _after(query, position):
    source, batch, index, row_id = (
        position.source,
        position.batch,
        position.position,
        position.row_id,
    )
    prefix = "batch_acceptance__candidate__batch__"
    return query.filter(
        Q(**{prefix + "operation__source_code__gt": source})
        | Q(**{prefix + "operation__source_code": source, prefix + "ordinal__gt": batch})
        | Q(
            **{
                prefix + "operation__source_code": source,
                prefix + "ordinal": batch,
                "batch_position__gt": index,
            }
        )
        | Q(
            **{
                prefix + "operation__source_code": source,
                prefix + "ordinal": batch,
                "batch_position": index,
                "id__gt": row_id,
            }
        )
    )


def _visible(row, rights, search, now):
    fields = row.fields
    operation = row.batch_acceptance.candidate.batch.operation
    if (
        row.batch_acceptance.source_code != operation.source_code
        or not 1 <= row.batch_position <= PAGE_SIZE
        or not row.record_ref
        or row.erased_at is not None
        or row.delete_at <= now
        or row.purpose != rights["purpose"]
        or row.retention_version != rights["retention_version"]
        or row.country not in search["countries"]
        or row.category not in search["categories"]
        or not isinstance(fields, dict)
        or not {"business_name", "phone"} <= set(fields)
        or not set(fields)
        <= set(rights["display_fields"]) & set(rights["storage_fields"]) & ALLOWED_FIELDS
        or any(
            not isinstance(v, str)
            or not v.strip()
            or len(v) > 2000
            or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for v in fields.values()
        )
        or not isinstance(row.field_lineage, dict)
        or set(row.field_lineage) != set(fields)
        or any(v != row.record_ref for v in row.field_lineage.values())
    ):
        return None
    entry = {
        "id": str(row.pk),
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
        return None
    return entry


def _noeffect_matches(operation, event, reserved_leads):
    """Match the durable no-effect batch identity set recorded at settlement."""
    batches = list(ResultBatch.objects.filter(operation=operation).order_by("ordinal")[:1001])
    candidates = list(BatchCandidateEvidence.objects.filter(batch__operation=operation))
    by_batch = {item.batch_id: item for item in candidates}
    batch_ids = {batch.pk for batch in batches}
    if (
        event.source_code != operation.source_code
        or event.provider_calls != 0
        or not 1
        <= len(batches)
        == event.batch_count
        <= min(1000, operation.call_limit, reserved_leads)
        or len(by_batch) != len(candidates)
        or any(batch.ordinal != index for index, batch in enumerate(batches, 1))
        or any(
            item.source_code != operation.source_code or item.batch_id not in batch_ids
            for item in candidates
        )
    ):
        return False
    batch_set = sorted(
        (
            {
                "batch_id": str(batch.pk),
                "candidate_body_hash": (
                    by_batch[batch.pk].body_hash if batch.pk in by_batch else None
                ),
            }
            for batch in batches
        ),
        key=lambda item: item["batch_id"],
    )
    encoded = json.dumps(batch_set, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest() == event.batch_set_hash


@transaction.atomic
def batch_results_page(
    user, workspace_id, job_id, cursor=None, *, country="", category="", source=""
):
    """Read at most 25 accepted positions; unavailable until explicitly enabled."""
    if settings.SAAS_BATCH_PAGE_READ_ENABLED is not True:
        raise PermissionDenied("Batch result pages are unavailable.")
    require_page_signing_key()
    locked_workspace(user, workspace_id)
    validate_filters(country, category, source)
    job = Job.objects.select_for_update().filter(pk=job_id, workspace_id=workspace_id).first()
    if job is None:
        raise Http404("Workspace resource not found.")
    categories = filter_options(job.search, "categories", 120)
    sources = filter_options(job.search, "source_codes", 64)
    for choice, options in ((category, categories), (source, sources)):
        if choice and int(choice) >= len(options):
            raise ValidationError("Result filter is outside saved search scope.")
    intent = JobOutbox.objects.select_for_update().filter(job=job).first()
    entitlement = Entitlement.objects.filter(workspace_id=workspace_id).first()
    if entitlement is None or not entitlement.is_current:
        raise PermissionDenied("Workspace entitlement is inactive.")
    reservation = None
    if intent is not None:
        reservation = UsageReservation.objects.filter(
            pk=intent.reservation_id, workspace_id=workspace_id
        ).first()
    if (
        intent is None
        or intent.result_protocol != 3
        or intent.status != "done"
        or job.status != "completed"
        or not 1 <= job.result_count <= 1000
        or reservation is None
        or reservation.status != "settled"
        or job.result_count > reservation.leads
        or job.result_count > job.search["result_limit"]
    ):
        raise RevisionConflict()
    try:
        snapshot, _ = eligible_sources(job.search)
    except (PermissionDenied, ValidationError):
        raise PermissionDenied("Current source rights are unavailable.") from None
    if snapshot != intent.source_snapshot:
        raise PermissionDenied("Current source policy differs from the job.")
    operations = list(
        DispatchOperation.objects.filter(
            job=job, outbox=intent, workspace_id=workspace_id
        ).order_by("source_code")[:13]
    )
    if (
        not 1 <= len(operations) <= 12
        or len({op.source_code for op in operations}) != len(operations)
        or {op.source_code for op in operations} != set(snapshot)
        or any(
            op.status not in {"success", "noeffect"}
            or op.request_hash != job.request_hash
            or snapshot[op.source_code]
            != {"version": op.policy_version, "hash": op.policy_fingerprint}
            for op in operations
        )
    ):
        raise RevisionConflict()
    finals = list(SourceBatchTerminal.objects.filter(operation__in=operations))
    noeffects = list(SourceBatchNoEffect.objects.filter(operation__in=operations))
    positive = {op.pk for op in operations if op.status == "success"}
    zero = {op.pk for op in operations if op.status == "noeffect"}
    settlement = reservation.settlement
    if (
        {item.operation_id for item in finals} != positive
        or {item.operation_id for item in noeffects} != zero
        or len(finals) != len(positive)
        or len(noeffects) != len(zero)
        or sum(final.accepted_count for final in finals) != job.result_count
        or type(settlement) is not dict
        or set(settlement) != {"leads", "jobs", "provider_calls", "exports"}
        or settlement
        != {
            "leads": job.result_count,
            "jobs": 1,
            "provider_calls": sum(final.provider_calls for final in finals),
            "exports": 0,
        }
        or settlement["provider_calls"] > reservation.provider_calls
    ):
        raise RevisionConflict()
    for op in operations:
        final = next((item for item in finals if item.operation_id == op.pk), None)
        noeffect = next((item for item in noeffects if item.operation_id == op.pk), None)
        batch_counts = BatchAcceptance.objects.filter(candidate__batch__operation=op).aggregate(
            total=Sum("accepted_count"), calls=Sum("provider_calls")
        )
        if op.status == "noeffect":
            if (
                noeffect is None
                or not _noeffect_matches(op, noeffect, reservation.leads)
                or batch_counts["total"] is not None
                or batch_counts["calls"] is not None
                or AcceptedResult.objects.filter(
                    workspace_id=workspace_id,
                    job=job,
                    batch_acceptance__candidate__batch__operation=op,
                ).exists()
            ):
                raise RevisionConflict()
            continue
        if (
            final is None
            or final.source_code != op.source_code
            or final.provider_calls > op.call_limit
            or batch_counts["total"] != final.accepted_count
            or batch_counts["calls"] > final.provider_calls
            or AcceptedResult.objects.filter(
                workspace_id=workspace_id,
                job=job,
                batch_acceptance__candidate__batch__operation=op,
            ).count()
            != final.accepted_count
        ):
            raise RevisionConflict()
    rights = {
        op.source_code: _rights(SourcePolicy.objects.get(pk=op.source_code)) for op in operations
    }
    prefix = "batch_acceptance__candidate__batch__"
    rows = (
        AcceptedResult.objects.filter(
            workspace_id=workspace_id,
            job=job,
            batch_acceptance__isnull=False,
            **{prefix + "operation__outbox": intent},
        )
        .select_related(prefix + "operation", "batch_acceptance__candidate__batch")
        .order_by(prefix + "operation__source_code", prefix + "ordinal", "batch_position", "id")
    )
    if rows.count() != job.result_count:
        raise RevisionConflict()
    upper_row = rows.last()
    if upper_row is None:
        raise RevisionConflict()
    upper = _position(upper_row)
    last = None
    if cursor is not None:
        continuation = decode_page_cursor(
            cursor,
            workspace_id,
            job_id,
            user.pk,
            job.request_hash,
            country=country,
            category=category,
            source=source,
        )
        if continuation.watermark != upper:
            raise RevisionConflict()
        last = continuation.after
    if country:
        rows = rows.filter(country=country)
    if category:
        rows = rows.filter(category=categories[int(category)])
    if source:
        rows = rows.filter(**{prefix + "operation__source_code": sources[int(source)]})
    if last is not None:
        rows = _after(rows, last)
    page = list(rows[: PAGE_SIZE + 1])
    now = timezone.now()
    visible = []
    for row in page[:PAGE_SIZE]:
        entry = _visible(row, rights[_position(row).source], job.search, now)
        if entry is not None:
            visible.append(entry)
    next_cursor = None
    if len(page) > PAGE_SIZE:
        next_cursor = encode_page_cursor(
            workspace_id,
            job_id,
            user.pk,
            job.request_hash,
            upper,
            _position(page[PAGE_SIZE - 1]),
            country=country,
            category=category,
            source=source,
        )
    return {
        "workspace_id": str(workspace_id),
        "job_id": str(job_id),
        "results": visible,
        "withheld_count": min(len(page), PAGE_SIZE) - len(visible),
        "next_cursor": next_cursor,
        "country": country,
        "category_filter": category,
        "source_filter": source,
        "category_options": categories,
        "source_options": sources,
        "can_review_export": False,
    }
