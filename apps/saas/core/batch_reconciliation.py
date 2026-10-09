"""Pure bounds for a complete signed v3 source set; no accounting authority."""

from dataclasses import dataclass
from uuid import UUID

from rest_framework.exceptions import ValidationError


@dataclass(frozen=True, slots=True, repr=False)
class SourceEvidenceTotals:
    operation_id: UUID
    source_code: str
    operation_status: str
    outcome: str
    call_limit: int
    allocated_batches: int
    accepted_leads: int
    accepted_calls: int
    final_calls: int


@dataclass(frozen=True, slots=True, repr=False)
class ReconciledEvidenceTotals:
    leads: int
    provider_calls: int
    positive_operation_ids: tuple[UUID, ...]
    noeffect_operation_ids: tuple[UUID, ...]


def bounded_source_evidence(sources, expected_sources, reserved_leads, reserved_calls):
    """Bound explicit source outcomes to original caps, without settling them.

    The caller must separately lock and authenticate current actor/source/key,
    original job/reservation and each complete durable allocation, candidate,
    accepted payload, signed final or signed no-effect proof. This calculation
    cannot establish source authority or make an unknown effect disappear.
    """
    if (
        type(sources) is not tuple
        or not 1 <= len(sources) <= 12
        or type(expected_sources) is not frozenset
        or len(expected_sources) != len(sources)
        or type(reserved_leads) is not int
        or not 1 <= reserved_leads <= 2147483647
        or type(reserved_calls) is not int
        or not 1 <= reserved_calls <= 2147483647
    ):
        raise ValidationError("Complete source evidence is unavailable.")
    ids, codes, positive, noeffect = set(), set(), [], []
    leads = calls = 0
    for item in sources:
        if (
            not isinstance(item, SourceEvidenceTotals)
            or not isinstance(item.operation_id, UUID)
            or item.operation_id in ids
            or type(item.source_code) is not str
            or item.source_code not in expected_sources
            or item.source_code in codes
            or type(item.operation_status) is not str
            or item.operation_status not in {"started", "unknown"}
            or any(
                type(value) is not int or not 0 <= value <= 2147483647
                for value in (
                    item.call_limit,
                    item.allocated_batches,
                    item.accepted_leads,
                    item.accepted_calls,
                    item.final_calls,
                )
            )
            or item.call_limit < 1
            or not 1
            <= item.allocated_batches
            <= min(1000, item.call_limit, reserved_leads, reserved_calls)
        ):
            raise ValidationError("Complete source evidence is unavailable.")
        if item.outcome == "source-final":
            if (
                not item.allocated_batches <= item.accepted_leads <= 25 * item.allocated_batches
                or not item.allocated_batches <= item.accepted_calls <= item.final_calls
                or item.final_calls > item.call_limit
            ):
                raise ValidationError("Complete source evidence is unavailable.")
            positive.append(item.operation_id)
        elif item.outcome == "source-noeffect":
            if any((item.accepted_leads, item.accepted_calls, item.final_calls)):
                raise ValidationError("Complete source evidence is unavailable.")
            noeffect.append(item.operation_id)
        else:
            raise ValidationError("Complete source evidence is unavailable.")
        ids.add(item.operation_id)
        codes.add(item.source_code)
        leads += item.accepted_leads
        calls += item.final_calls
    if codes != expected_sources or leads > reserved_leads or calls > reserved_calls:
        raise ValidationError("Complete source evidence is unavailable.")
    return ReconciledEvidenceTotals(leads, calls, tuple(sorted(positive)), tuple(sorted(noeffect)))
