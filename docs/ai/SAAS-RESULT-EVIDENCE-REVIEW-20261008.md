# Candidate result evidence: internal preflight

## Delivered boundary

`core.result_evidence.review_candidates` is an internal read-only review service, with no route, worker, source activation or accepted-result store. It rechecks membership/role, current active entitlement, tenant/job/outbox/attempt/reservation identity and running/unsettled state under the existing workspace lock. Current source switches, capability/evidence/control checks and fingerprint reuse `eligible_sources`; any policy change invalidates the saved operation. Members may review, viewers cannot; revoked/foreign access fails closed.

The separate version-1 candidate envelope is exact-byte HMAC verified through `SAAS_RESULT_VERIFIERS`, empty by default and distinct from terminal receipt keys. It binds workspace/job/operation/source/provider key/request hash/policy fingerprint and includes a bounded event reference, issue time and 1–25 candidate records, within search/reservation/current entitlement bounds. Unknown/duplicate JSON fields, oversized bodies, deep JSON, unsigned bodies, altered bytes and malformed metadata fail closed without leaking payloads in errors.

Each record binds a source record reference, US/CA country and requested category/status, observed timestamp, purpose and retention version, business name/normalized NANP phone, allowlisted bounded fields and exact field-to-record lineage. Explicit versioned `controls.result_contract` metadata must permit display/storage for every supplied field, declare purpose/retention version and a maximum age of 1–2,592,000 seconds. Missing, unknown or loosely typed rights are denied. Deadline is observed time plus that maximum age and must remain in the future. The structured metadata is part of the existing policy fingerprint; synthetic fixtures are not real provider rights.

The frozen return contains only event reference, exact body digest, candidate count and earliest deletion deadline. It contains no lead payload, signature or secret. Same bytes yield the same digest; changed bytes yield a different digest. This is comparison evidence, **not durable replay/conflict resolution, exact R2 dedupe, an accepted-lead proof, storage authorization or a usage settlement grant**. Phone syntax does not prove reachability or geographic accuracy. No records, accounting counters, receipts or job states are written. Existing terminal receipts still settle zero leads/exports.

## Review and verification

Ten new tests cover redacted immutable/repeated review, unchanged accounting, unconfigured/separate verifier keys, forged/bound identities, exact schema, duplicate/deep/oversized payloads, scope/phone/lineage/rights/retention failures, live policy drift/kill switch, viewer/revoked/foreign/inactive access, reservation caps and zero-result terminal receipt compatibility. Local full suite and exact-head PostgreSQL/required/Web CI must pass before merge; repository checkpoint records final evidence after verification. No schema migration is introduced.

## Next acceptance gates

Add durable event collision/replay records and a reviewed versioned nonzero result/accounting contract before storing accepted results. Preserve production exact R2 authority and isolated SaaS namespaces; candidate input cannot assert uniqueness. Then implement bounded tenant reads and source-aware export authorization/field rights, atomic export caps, safe CSV output, retention/deletion/tombstones and privacy-safe audits together. Current preflight has no export permission or export endpoint. Source/provider review, encryption/physical deletion/backup acceptance, deployment and customer/browser validation remain external or subsequent implementation work.
