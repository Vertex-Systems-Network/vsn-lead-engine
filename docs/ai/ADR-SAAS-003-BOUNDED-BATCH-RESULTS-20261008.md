# ADR-SAAS-003: additive bounded batch intake and result pagination

Status: accepted internal development direction under standing technical autonomy; inert durable metadata schema and pure batch/terminal proof verified through PRs #209/#211/#212; transactional intake/accounting and pagination not delivered. Date: 2026-10-08. No provider, signer, payment, scheduler or production activation is authorized by this ADR.

## Evidence and problem

The delivered v2 path is deliberately one operation/source/batch, 1–25 accepted records, one candidate event and one terminal acceptance per operation. `accept_results` rejects multiple operations, requires a zero-result running job, settles the whole reservation and completes the job. `results_snapshot` reads the first acceptance and refuses more than 25 stored rows. These explicit guards preserve the current tested contract. Increasing a slice limit or reusing v2 for partial batches would bypass quota/accounting/visibility guarantees.

## Decision

Implement an additive v3 batch protocol and separate trusted internal intake service. Preserve the current v1 zero-lead terminal receipts, v2 candidate/accepted-result services, URLs and HTTP/export semantics. Do not allow mixed v2/v3 acceptance within a job. A trusted local job protocol selector defaults to the delivered v2 path; new v3 jobs need separately reviewed source/signer capability and never become active merely from client request JSON.

A pure, disabled normalized manifest validator is the next independently reviewable slice. It must accept only trusted local operation/job/workspace/source/batch coordinates and source/qualification/dedupe authorities, bounded exact-byte envelopes with duplicate-key rejection, short issuance/deadline bounds and an explicit v3 kind. The validator itself must have no ORM, network, key provisioning, billing, job transition or accepted-result writes. Fixtures never become source-rights evidence. Durable identity/ordering/limits are future transactional gates, not claims a signature can establish.

Future source batches have a server-owned immutable batch identity tied to operation, immutable request/policy identity and stable dispatch/provider idempotency key. Candidate/acceptance references are unique per source; exact-body replay returns the existing decision, changed-body/key/reference reuse conflicts. Each batch contains 1–25 records and bounded provider usage. The sum of accepted batches never exceeds the original reserved lead count or current grant/rights bounds. Every record still requires canonical phone qualification, US/Canada scope, taxonomy precision, explicit source rights and independently attested committed exact isolated R2 fingerprints. No arbitrary larger job target may mint data or weaken existing qualification.

Do not settle/release the whole reservation on the first batch. Persist each verified batch, tenant fingerprint backstop and payload atomically under the existing workspace lock. Track bounded accrued actual usage separately from final settled counters; retain the entire original reservation while any source outcome/final marker is unknown. Final whole-job reconciliation derives totals from durable batch evidence, checks reservation/period/caps and settles once. Confirmed no-effect and pending safe-cancellation paths remain separate. Unknown effects cannot be inferred cancelled, refunded or retried. A trusted final-source manifest must bind exact batch identities and terminal provider-call totals; gaps/conflicts require reconciliation rather than guessed completeness.

Pagination is additive and bounded to 25 displayed results per response and signed continuations bound to actor/workspace/job/request/filter identity, immutable upper watermark and expiry. Use stable stored sequence plus UUID tie-breaker; each page rechecks membership, grant deadline and current source rights/retention before emitting fields. Do not preload every payload to paginate. New inserts beyond the watermark do not enter an existing continuation. Erased/expired/revoked rows remain withheld; visible/filtered/withheld/page counts must be explicitly scoped so they do not imply total delivery or resurrect deleted payloads.

Exports remain explicit current selection of at most 25 rows with short-lived signed actor/job/page/filter/field scope, current intersected source grants and once-only prepared-file accounting. A cursor or row ID does not grant export authority. Continuations, signed previews and redacted histories require no-referrer and protected access-log handling before deployment. Never retain raw signed events, source records, CSVs or keys just to simplify recovery.

## Migration and verification sequence

1. Pure bounded v3 manifest validator plus adversarial DB-forbidden tests; separate empty-default authority and no consumer/endpoint.
2. Add durable batch and terminal-manifest models with uniqueness/order/cap constraints, legacy protocol classification and evidence-preserving rollback. Preserve all existing v2 rows and references.
3. Atomic batch reconciliation and final whole-job settlement; PostgreSQL duplicate/conflicting-batch, cross-job reference reuse, concurrent cap, terminal/partial, expiry/revocation, crash/rollback and period races. Test that unknown work keeps its reservation.
4. Tenant-scoped keyset page contract/service with signed watermark/filter context, live rights/grant checks, payload-size limits and no full-payload scan.
5. Native Next continuation and selected-page CSV flows with actual Django/Next HTTP auth/CSRF/filter/replay/erasure tests. Browser/keyboard/WCAG/customer acceptance remains separate.
6. Real signer/source/rights/key lifecycle/crash reconciliation, backup/retention/encryption and deployment acceptance before any activation.

## Trade-off and scope

An additive protocol costs new models and explicit reconciliation, but preserves the known v2 accounting boundary. Broadly rewriting acceptance or raising the current 25-row limit is rejected because the existing job finalization is terminal. No stack change, paid dependency, pricing decision, source rights claim, core ANPOS protocol change or external launch commitment is needed for the pure development slice. Broader product milestones remain in progress; this ADR is architecture evidence only.

## Pure manifest slice

`core.batch_manifest` has no ORM/network or state writes. Trusted immutable coordinates include batch/operation/provider/candidate/request/policy identity and reserved bounds; signatures use separate source/isolated-registry registries with empty defaults. Exact bytes, strict v3 kind, duplicate-key denial, bounded 1–25 unique record/fingerprint triples, short issuance and provider-call caps are checked. Returned immutable redacted evidence has no record payload/tokens/signature/secret. Ten adversarial `SimpleTestCase` cases forbid database access. No accepted record, durable batch, ordering/idempotency, terminal settlement or source qualification truth is created by verification.

## Verified pure proof checkpoint

PR #209 merged at 176f8309a1d68c2feb650898d240bd2ed5aa89fc; head 7c5adceb3fb150a89aaed3c8f556aea2552602f4 passed all five CI workflows, PostgreSQL 37812348239 (306 tests/migrations/settings) and Web 37812348326 (14 transport/build/type/HTTP). Ten DB-forbidden v3 proof cases; no intake/ledger/activation. PRs #207/#208 billing ledger/expiry/diagnostics remain verified.


## Durable metadata and terminal-proof contract

PR #211 adds inert batch/candidate/acceptance/source-terminal metadata with
uniqueness/count constraints and protected reversal (see schema contract). No
legacy classification or v3 intake is enabled by the schema. Existing v2 behavior
remains the sole active service contract; explicit server-side enrollment and
cross-version exclusion must precede any v3 writes.

The next pure source-final proof uses a canonical UUID-sorted list of accepted
batch identities, acceptance-body SHA-256 digests, accepted counts and accrued
calls. It binds workspace/job/operation/provider/request/policy/source, exact-byte
HMAC from a separate empty-default terminal registry, a 24-hour/five-minute issuance
window and at most 1,000 batches / 256 KiB. Its exact-set digest is SHA-256 of
ASCII JSON rows with sorted object keys and compact separators. Terminal calls
may exceed summed accepted-batch calls (rejected discovery still costs calls), but
must cover accrued calls and remain within the trusted reserved source budget.
An empty accepted set may report calls; it never implies a refund/no-effect.

The trusted caller must independently derive all accepted coordinates from locked
durable evidence and reconcile every allocated identity/candidate/unknown source
effect. Exact accepted-set equality is not proof that an allocated or provider
batch was never omitted. A signature alone never closes an unknown effect or
settles capacity. Exact-body replay/conflict, current rights/grants, crash-safe
persistence and final whole-job settlement remain transactional service work.


## Verified terminal-proof checkpoint

PR #212 merged at 20e2362ec6000a72e679a8716d428795f1a9d077; head b0f19291687c8b532b81a2f2bdd85e8c29758e9a passed all five workflows, PostgreSQL 37816828169 (329 tests/migrations/settings) and Web 37816828126 (14 transport/build/type/HTTP). Ten DB-forbidden bounded source-final proof cases; no enrollment/intake/finality/settlement authority.


## Quarantined enrollment checkpoint

Migration 0019 defaults existing/new outboxes to v2 without reclassifying old
evidence. Disabled trusted-local admin enrollment selects v3 only on a pending
queued job before any attempt. Replay rechecks current actor/source/grant/cap and
period/deadline gates without changing job revision or accounting. The explicit
source allowlist is empty by default. Ordinary pre-dispatch always refuses v3;
v1/v2 proof services refuse its selector before processing evidence. Pending safe
cancellation is preserved. Populated v3 classification blocks destructive reversal.

This is a deliberate quarantine until a separately reviewed internal v3
write-ahead/identity/candidate/acceptance/finality path can preserve every original
reservation. No public selector, source caller, scheduler, signer or network
consumer is added. The enrollment preflight override is internal validation only;
it is not a dispatch authorization or client-controlled parameter.

PR #214 merged at 412c29286500d8db88491e13074baa77a7648eb5; head f68067283ab1ab16d437e8bd4093a182ab4cda01 passed all five workflows, PostgreSQL 37821424861 (338 tests/migrations/settings) and Web 37821424914 (14 transport/build/type/HTTP). Disabled quarantined admin v3 enrollment, default-v2 classification, legacy proof exclusion and preserved cancellation; no allocation/intake/dispatch.

## Verified allocation and candidate ledger checkpoint

PR #218 merged at 15814cf0bf0c52f58c4b1d1e31cc208bc3445199; head f9d0173c03fac4a757a605dfed3e30f38c98cb3e passed all five workflows, PostgreSQL 37824615261 (366 tests/migrations/settings) and Web 37824615227 (14 transport/build/type/HTTP). Disabled durable redacted candidate ledger, exact replay/reference conflicts and unknown-effect preservation; no accepted payload/finality/dispatch.

Allocation (#216) and pure candidate proof (#217) precede this disabled ledger. Candidate payload is not retained by this ledger; current proof/rights and all original caps are rechecked for replay. Unknown operations permit existing exact replay but reject new candidate evidence. Add isolated v3 accepted-payload schema with evidence-preserving rollback, then gated atomic acceptance and exact terminal/unknown-effect accounting; preserve original reservations. Internal write-ahead entry and signed 25-row pagination follow. Ordinary v3 dispatch remains quarantined.

## Shared payload and fingerprint boundary

The additive payload schema reuses `AcceptedResult` with an exclusive nullable legacy/v3 acceptance link and a bounded per-batch position. Existing rows keep their original required legacy link through a database exclusive-or constraint. This preserves a single tenant/token uniqueness authority and the existing deadline/erasure service across both versions. Separate payload/fingerprint tables were rejected because they would split the transactional tenant dedupe backstop and duplicate retention logic. Isolated signed R2 proof remains mandatory; local uniqueness is only a backstop.

V3 rows do not enter legacy acceptance-scoped reads, and the v2 snapshot explicitly withholds protocol-3 intents even in a synthetically mixed state. No v3 serializer/endpoint/consumer is added. Future pagination may bind an acceptance-ID upper watermark and batch position/UUID keyset; it must prove payload immutability, visibility and current rights in a separately reviewed service. Populated v3 payloads and tombstones block reversal before any constraint/column removal; legacy-only reversal/reapply preserves row identifiers, fields, lineage, deadlines and fingerprints. Schema writes do not update job/reservation/counters. Cross-tenant/job/source link agreement and aggregate budgets remain service invariants, not database proof.
