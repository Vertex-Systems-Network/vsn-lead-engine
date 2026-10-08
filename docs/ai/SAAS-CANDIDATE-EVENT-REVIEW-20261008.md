# Redacted candidate event ledger

## Scope and authority

This slice follows the verified PR #188 candidate preflight. Internal `record_candidate_review` runs that same preflight inside one transaction and retains the workspace/operation/source locks until the redacted evidence row commits. All replays recheck current membership, entitlement, unsettled operation, source fingerprint and candidate expiry first. There is no endpoint or provider/consumer activation. The verifier registry remains empty by default.

`CandidateEvidence` retains operation identity, source code, bounded event reference, exact-byte body hash, candidate count, earliest candidate deletion deadline and recording timestamp. It contains no lead payload, source record references, credentials or signatures. The protected operation points to its tenant/job/attempt and saved policy identity. One event per operation is the deliberately bounded initial contract; multi-batch intake requires a separately versioned contract.

Same operation and bytes replay the original row without updating its time/deadline. Different valid bytes or event references conflict. A database source/event uniqueness constraint also prevents valid evidence being rebound across jobs/workspaces. The service converts constraint collisions to generic conflict without disclosing another tenant. Duplicate/conflicting calls serialize under workspace locks; cross-workspace collision is enforced by the database unique constraint. Failed writes roll back. These rows are comparison/audit evidence, not accepted results, R2 uniqueness proof or a usage settlement grant. Terminal receipts remain compatible and still settle zero leads/exports.

## Migration and verification

Additive migration 0012 creates only the isolated SaaS metadata table, count bounds 1–25, unique source/event and protected one-to-one operation. Empty-database reversal/reapplication remains supported; a populated ledger refuses destructive reversal pending an explicit evidence preservation/reconciliation plan. No production R2/workbook schema or records are touched.

Ten new tests cover unchanged accounting, identical replay, changed payload/event conflicts, signed cross-workspace collision, current rights/role/expiry rechecks, unconfigured verification, injected-write rollback, database constraints, protected parent/reverse guard and three PostgreSQL races (duplicate, conflicting, cross-workspace). PR #189 merged at 0a81b3e24f45edfa72b5101c8241891030a88f1c; head fb58dd787290a81813f3c85a412f897782b5ffd7 passed required checks/Actions CodeQL, PostgreSQL 37770588647 (all 182 tests, including three candidate-event races, migrations/settings) and Next/HTTP 37770588715 (nine transport tests/build/type and native workflows). Local SaaS: 163 passed/19 PostgreSQL-only skips; root 376 passed/1 skipped/28 subtests, Ruff/ANPOS and drift pass.

## Remaining gates

No accepted-result store or nonzero accounting is implemented. Provenance signatures and syntax cannot prove source rights, phone reachability, territory accuracy or exact cross-day uniqueness. Accepted ingestion needs a reviewed versioned receipt/accounting contract, trusted dedupe evidence and atomic lead budgets. Results reads/export follow with source field/export rights, atomic export caps, safe CSV, revocation/deletion/tombstones and audits.

The earliest deadline describes candidate freshness/retention eligibility; no payload was retained and no physical cleanup runs. Redacted audit metadata retention/deletion/backup policy remains a separate production acceptance gate. Event references are provider audit identifiers and must not contain personal data; operators must enforce this when onboarding an adapter. No public/customer/browser/deployment/legal or live collection certification follows from these tests.

## Subsequent verified implementation

PRs #191–#192 supersede the historical unimplemented storage/read claims in this review: internal dual-attested accepted storage/nonzero v2 accounting and bounded current-rights Next results reads are verified. Candidate review/event rows alone still grant no acceptance or dedupe authority. Live signer/R2 integration, export and physical retention cleanup remain open. See the accepted-results and Next-results reviews.
