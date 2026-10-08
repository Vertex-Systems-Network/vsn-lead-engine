"""Pure whole-job v3 accounting preflight; no settlement or database authority."""

from dataclasses import dataclass
from uuid import UUID

from rest_framework.exceptions import ValidationError


@dataclass(frozen=True, slots=True, repr=False)
class SourceAccounting:
    operation_id: UUID
    source_code: str
    operation_status: str
    call_limit: int
    batch_count: int
    accepted_count: int
    committed_batch_calls: int
    final_provider_calls: int


@dataclass(frozen=True, slots=True, repr=False)
class CheckedSettlement:
    leads: int
    jobs: int
    provider_calls: int
    exports: int
    operation_ids: tuple[UUID, ...]


def checked_batch_settlement(sources, expected_sources, reserved_leads, reserved_calls):
    """Bound a trusted, complete final set to the original reservation.

    The caller must independently lock and verify actor, rights, every original
    operation/batch/acceptance/source-final, signed proofs, reservation and
    entitlement. This pure calculation never certifies those external facts.
    Empty or unknown/no-effect source outcomes remain unsupported.
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
        raise ValidationError("Whole-job batch accounting is unavailable.")
    seen_ids, seen_sources, leads, calls = set(), set(), 0, 0
    for item in sources:
        if (
            not isinstance(item, SourceAccounting)
            or not isinstance(item.operation_id, UUID)
            or item.operation_id in seen_ids
            or type(item.source_code) is not str
            or item.source_code not in expected_sources
            or item.source_code in seen_sources
            or item.operation_status != "started"
            or any(
                type(value) is not int or value < 1 or value > 2147483647
                for value in (
                    item.call_limit,
                    item.batch_count,
                    item.accepted_count,
                    item.committed_batch_calls,
                    item.final_provider_calls,
                )
            )
            or item.batch_count > min(1000, item.call_limit, reserved_leads, reserved_calls)
            or not item.batch_count <= item.accepted_count <= 25 * item.batch_count
            or not item.batch_count <= item.committed_batch_calls
            or not item.committed_batch_calls <= item.final_provider_calls <= item.call_limit
        ):
            raise ValidationError("Whole-job batch accounting is unavailable.")
        seen_ids.add(item.operation_id)
        seen_sources.add(item.source_code)
        leads += item.accepted_count
        calls += item.final_provider_calls
    if seen_sources != expected_sources or leads > reserved_leads or calls > reserved_calls:
        raise ValidationError("Whole-job batch accounting is unavailable.")
    return CheckedSettlement(leads, 1, calls, 0, tuple(sorted(seen_ids)))
