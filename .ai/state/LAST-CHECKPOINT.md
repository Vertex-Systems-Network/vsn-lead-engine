# Last Checkpoint

## Snapshot

- Vertex-Systems-Network/vsn-lead-engine; 2026-10-08 UTC / PKT.
- Protected feature main read `3336a81bdaf5fc2aaa6761c514f0a80d18b02fa7` / PR #204; feature base precedes documentation merge. Reconcile exact live main, open Issues then PRs before replay.
- Next.js/TypeScript frontend, Django/DRF/PostgreSQL authority; production CLI/R2/Google stays isolated.
- Open Issues: none at session start. Dependency PR #174 remains open (setup-node major update); separately review immutable action/runner compatibility before merging. No existing feature mutation replayed.

## Verified

- PR #204 merged at 3336a81bdaf5fc2aaa6761c514f0a80d18b02fa7; head 02516bda90cd6e1aea00983f75193da14e75d1ae passed all five CI workflows/required checks/Actions CodeQL, PostgreSQL 37798742414 (all 269 tests, migrations/reversal/settings and earlier concurrency) and Web 37798742458 (14 transport tests, lint/format/build/type and actual Next/Django HTTP flows). Ten DB-forbidden billing-evidence tests verify the pure validator; no entitlement/payment write or activation.
- Pure internal normalized billing evidence uses trusted local coordinates and empty default keys with bounded freshness/validity. It has no persistence, endpoint or entitlement/payment writes. Actual provider truth, durable uniqueness/order and ongoing capability expiry are not established by a signature.

- PR #202 merged at f4e7e5ee2aacb53c3e609acc7d039471455e0241; head 4d09b60b3fc04b23312f25e13b3f1ff703a59cd6 passed all five CI workflows, including required checks/Actions CodeQL, PostgreSQL 37797128235 (all 259 tests, concurrency, migrations/reversal/settings) and Web 37797128305 (14 transport tests, lint/format/build/type and actual HTTP scoped signed receipt navigation, no-charge/erasure/redaction/referrer headers and earlier native auth/filter/CSV flows).
- Readonly 25-row receipt history has current owner/admin job scope and member-own scope, viewer denial, signed 24-hour actor/job/scope-bound continuation, no charge/write/CSV and retained redacted metadata after payload erasure. Next/API no-referrer headers pass actual HTTP; live ingress/access-log query redaction remains a deployment gate. Migration 0016 indexes are reversible and passed PostgreSQL migration CI.

- PR #200 merged at 812a4bc20e661e3088e453c866f50c031dca3d6f; head 2c326478c98c6fbdb482c7c73270d6fa19092ae0 passed all required checks/Actions CodeQL, PostgreSQL 37793585524 (all 253 tests, concurrency, migrations/settings) and Web 37793585562 (13 transport tests, build/type and actual HTTP compound/empty/clear filters, filtered-row denial, subset-only CSV/replay/conflict, auth and two-row erasure/tombstones).
- Country/category/source native filters use saved metadata indices and current-rights AND matching; All/Clear and shown/filtered/withheld counts verified. Signed preview excludes even otherwise-authorized filtered-out rows. Six added backend cases and actual two-category HTTP subset CSV/erasure evidence pass. No migration, new payload copy or live activation.

- PR #198 merged at 7dd9f10b4c28b1bacea1488aee5874685f600e3a; head 141cbac20f05b9edc3f63a4374fbc3612766140c passed all required checks/Actions CodeQL, PostgreSQL 37784930553 (all 247 tests, concurrency, migrations/settings) and Web 37784930581 (12 transport tests, build/type and HTTP country-filter/selected-row CSV/empty denial/replay/conflict/erasure/auth flows).
- Country filters use only US/CA/All metadata in URLs; shown/filtered/withheld counts are distinct. Native CSRF row/field selection stays inside signed filtered scope; subset CSV/replay/changed-selection conflict, empty/duplicate/foreign/oversized input, old-form rejection and unselected erasure are tested. No migration or live consumer activation.

- PR #194 merged at 6f9ad2b7808471c67523e31f1b42d37a710d9cd8; head 5dde3934edb0fdc2424b2fe4bb0d5e41e2eb9a46 passed required checks/Actions CodeQL, PostgreSQL 37779435828 (223 tests/export races/migrations/settings) and Next/HTTP 37779435876 (10 transport tests/build/type and CSRF CSV/replay/viewer denial).
- PR #195 merged at 92657c5c8bbdb27115e95f5642f841e8a1c975c3; head dc84dce770bf14580e9d2691880510fc6615ba14 passed required checks/Actions CodeQL, PostgreSQL 37780165591 (235 tests/expiry races/migrations/settings) and Next/HTTP 37780165669 (10 transport tests/build/type and payload erasure/tombstone flow).
- PR #196 merged at 584ba0ad71557609e88b4d5b48816f41f2dfd563; head 10f5ee5bc42f033f5d162a0ab5ef3232d330e963 passed required checks/Actions CodeQL, PostgreSQL 37781243971 (all 241 tests/concurrency/migrations/settings) and Next/HTTP 37781243921 (11 transport tests/build/type and native preview/confirmed CSV/replay/conflict/erasure flows).
- Source-aware 1–25-record CSV preparation requires explicit field grants/current rights, CSRF and member role. Atomic caps include pending reservations; one unit per prepared file. Redacted keyed digest ledger retains no CSV; identical actor/key/specification replays once and changed selection/content conflicts.
- Explicit current-admin source-expiry erasure clears active fields/lineage/source ref/category/purpose/retention label, keeping dated actor tombstones, fingerprints and usage/counts. Duplicate/rollback/role/expiry races and retained later-job duplicate rejection tested. No scheduled cleanup activated.
- Native Next preview shows count, field omissions, attribution, earliest deadline and one-unit notice. Signed confirmation scopes actor/tenant/job/rows/permitted fields and short expiry. Direct Django CSRF POST returns CSV; viewer action omitted and failure review mints no new authority.
- Earlier candidate/accepted-store/receipt/job/account/native forms remain verified. All 269 PostgreSQL tests pass; local 243 pass/26 PG-only skips; Next 14 transport/lint/format/build/type and real HTTP pass. Root 376 pass/1 skip/28 subtests; Ruff/ANPOS pass. CodeQL scans Actions only.
- M5 85%, M6 75%, M7 86%, overall ~52% engineering indicators. Work units unchanged: 9 complete, 5 in progress, 1 blocked, 2 deferred, 4 not started of 21.

## Not Verified

- Real isolated R2 signer/client/qualification bridge, live intake/source/provider/payment/scheduler and Next production deployment remain disabled. Synthetic proofs/rights are fixtures only.
- Broader batch pagination, billing events, recovery/signup, browser/responsive/WCAG/customer, encryption/backup/audit-retention and TLS/proxy acceptance remain open. HTTP is not browser certification.
- Retained production quota is 6,855/12,000 on 2026-10-04; no fresh quota observation. Distributed runtime identity unverified; no work after turn end claimed.

## Known Risk

- Trusted future signer must prove canonical phone qualification/exact committed isolated R2 fingerprints, keys and crash reconciliation. Signature/schema tests do not prove actual signer behavior or commercial rights.
- Active payload erasure is irreversible. Tombstone fingerprints/actor/job/country metadata remain pseudonymous; WAL/replicas/backups/client/downstream CSV erasure and qualified retention review are not certified. DATA-006/007/008 record remaining gates.
- CSV charge is preparation, not successful delivery. Current rights/expiry can deny replay; SECRET_KEY rotation fails digest replay closed. No retained CSV exists for recovery beyond current rows.
- Unknown provider effects retain reserved capacity. ESLint 9/plugin compatibility EOL remains a production gate. Default policies/verifier registries stay unavailable.

## Next Action

1. Implement disabled durable billing bindings/redacted event ledger and atomic exact replay/contiguous revisions; enforce entitlement validity across every capability before enabling writes or billing. Preserve all reservations/periods; no live payment/provider activation.
2. Billing-event reconciliation is independent safe work; audit/fingerprint/backup retention policy and real signer/source/legal/customer evidence remain separate before-production gates.
3. Continue the ready frontier within invocation budget; checkpoints are recovery aids, not permission gates.
