# V3 batch metadata schema and migration contract

Development scope under ADR-SAAS-003. Migration 0018 is additive: it neither alters
v1/v2 tables nor backfills, moves or accepts production data. No v3 endpoint,
command, consumer, signer or accounting service is enabled by this change.

| Table | Durable coordinate | Database guarantee |
| --- | --- | --- |
| ResultBatch | UUID, dispatch operation, ordinal | Positive ordinal; one ordinal per operation |
| BatchCandidateEvidence | Batch, source/event reference, digest/count/deadline | One candidate per batch; unique source/event reference; 1–25 count |
| BatchAcceptance | Candidate, source/receipt reference, independent key identifiers, digest/namespace/count/calls/time | One acceptance per candidate; unique source/receipt reference; 1–25 count; positive calls |
| SourceBatchTerminal | Operation, source/receipt reference, digest, exact-set digest/count/accepted/call totals/time | One terminal per operation; unique source/receipt reference; zero batches implies zero accepted; otherwise 1–25 accepted per batch and positive calls |

All evidence links use PROTECT. Raw signed bytes, signatures, lead payloads and
fingerprint tokens are absent. Digests/references remain pseudonymous evidence;
this is not a privacy or retention certification. The final-set digest is a
coordinate only until a verifier derives it from an exact, bounded signed set.
Zero-batch terminals can still attest calls with no accepted results; no refund
or no-effect outcome may be inferred from the accepted count alone.

Foreign keys do not verify cross-table source/tenant equality, authorized current
rights, immutable dispatch policy, or signer truth. Constraints do not establish
aggregate reservation caps, exact-body replay, ordering continuity, terminal
completeness or cross-version exclusion. A later trusted-local gated service must
lock workspace/job/outbox/reservation, establish a server-owned protocol selection,
reject v1/v2 evidence for a v3 job, compare all immutable coordinates, allocate
bounded identities, and keep full capacity reserved until every source is
independently final. Never expose ORM row creation as evidence acceptance.

Metadata writes intentionally leave job status/count, UsageCounter,
UsageReservation and AcceptedResult unchanged. V2 one-source whole-job accounting
remains authoritative for existing jobs. There is no model field or client JSON
switch that enables v3 today. Exact replay and settlement are service work, not
claims made by these tables or their uniqueness tests.

## Migration and recovery

Forward creation performs no existing-row scan, backfill or data transformation;
new empty tables and constraints are created. Actual production DDL locking,
backup/restore and deployment preflight remain unverified and required before a
production rollout. Empty reversal and reapplication are supported. Reverse
RunPython executes before dropping any new table and refuses reversal if any new
identity/evidence row exists, including identities with unknown effects. Preserve
history and roll forward; do not delete rows to evade the guard. PROTECT prevents
cascading evidence loss through parent deletion; it is not an append-only database
permission policy against privileged direct update/delete.

Local tests verify bounds, uniqueness, protected parent deletion, redacted fields,
reservation/payload preservation and reverse guard coverage. Three explicit
PostgreSQL-only races verify duplicate ordinal, source/event reference and terminal
exclusion. They are uniqueness races, not settlement/cap/replay certification.
All existing service races and forward/reverse/reapply CI remain required.
