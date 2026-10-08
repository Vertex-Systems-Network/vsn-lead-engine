# ADR-SAAS-005: isolated dual-attested result acceptance

Status: accepted for reversible development; live activation unavailable.

## Decision

Introduce a separate version-2 accepted-result receipt and isolated SaaS payload/fingerprint store. Keep version-1 terminal receipts unchanged at zero accepted leads. Require exact-byte signatures from both a source acceptance authority and an independent, workspace-bound R2/phone-qualification authority, plus the original signed candidate payload matching its durable candidate ledger. Signing registries remain empty and no HTTP intake/consumer is added.

The fixed registry namespace is `saas-results/v1/<workspace UUID>`, never the production collector namespace. The registry attestation declares `r2-exact-objects-v1`, `vsn-phone-usca-v1` and committed state for this exact candidate digest, event, operation and source. Its key must differ from source acceptance and candidate keys. The future trusted signer must verify canonical engine phone qualification and exact R2 fingerprint reservation/commit, not merely accept source claims. Signer integration, real R2 I/O, crash reconciliation and key lifecycle are **not implemented or certified by this application verifier**. No canonical fingerprint algorithm is copied or replaced.

This initial contract accepts one complete 1–25-record candidate batch for one source/operation; multi-source or multi-batch jobs fail closed. Receipts cover exactly all candidate references and source/phone-name/location tokens plus domain when a website is supplied. Tokens use the existing R2 96-bit BLAKE2 format. The future bridge maps licensed candidate fields to the canonical Lead contract (country names, name/phone/city/website/address, empty unsupported region/place ID, source ID scoped to source code and record ref); a candidate with unsupported canonical qualification/token output must be rejected before attestation.

Under the workspace lock, current admin membership, active entitlement, source rights/fingerprint and retention are rechecked. Results, tenant token uniqueness backstop, version-2 receipt, actual lead/job/provider usage and terminal job/outbox/attempt state commit together. Identical replay does not charge again; conflicting bytes/event/token collisions fail without replacement or refunds. A version-1 and version-2 terminalization cannot both commit. Tokens are a local defensive backstop; they do not replace required trusted isolated R2 evidence.

## Alternatives and consequences

- Trusting a requested limit or a candidate count would fabricate accepted outcomes; rejected.
- Treating existing zero-lead receipts as nonzero proofs would break compatibility/replay accounting; rejected.
- Copying production R2/workbooks into the tenant app or forking its normalization algorithm would weaken isolation/authority; rejected.
- Waiting for a live provider before implementing storage would unnecessarily block synthetic contract and concurrency verification; use empty-by-default authorities and no intake route.

Payloads are confidential customer/business-contact data. Source-derived purpose, retention version, field lineage and deletion deadline are stored; actual cleanup/tombstones, encryption, backups and customer export acceptance remain before-production gates. Populated evidence migrations refuse destructive reversal. Qualified source/privacy review and signer onboarding are external gates; no paid service or launch is approved.
