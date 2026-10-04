# VSN Lead Engine — ANPOS Requirements 83–96 Evidence

Evidence basis before this hardening branch: `ec525a1faac7e4e8b6e736ddc40261bde0275c26`.

This is project-specific engineering evidence, not a blanket legal or compliance certification.

## Runtime classification

VSN Lead Engine is a deterministic Python/GitHub-Actions data pipeline. Runtime lead acceptance uses taxonomy, phone validation, exact dedupe, public-source enrichment and scheduling code. No AI/ML/LLM/RAG model participates in production lead decisions. Development-time ANPOS/assistant tooling is control-plane tooling, not a runtime lead decision engine.

Therefore REQ-83, REQ-89 and REQ-92 are not applicable to the current runtime. REQ-84 is also not applicable to this release because the product has no interactive end-user UX surface; its primary output contract is a dated operational workbook.

## REQ-85 — outcome evidence

The product persists per-category/total accepted counts, shortfall, US/Canada balance, discovery/acceptance/duplicate/missing-phone funnels, enrichment recovery, partition/source yield, readiness incidents and recovery outcomes.

Primary evidence: `src/vsn_lead_engine/health.py`, `src/vsn_lead_engine/sheets.py`, README production status, Actions runs 37213320765 and 37225162383.

A successful workflow is never treated as automatic quota completion.

## REQ-87 — delivery safety

Selected delivery mode: protected-main direct release for a low-risk scheduled backend automation.

Controls: PR-only main changes, strict required checks, squash-only history, serialized production concurrency, main-only real schedules, runtime deadlines, active-run duplicate-dispatch guard, health evidence and a midnight runway stop. Run 37225162383 demonstrates the stop condition prevented unsafe late recovery.

## REQ-88 — engineering quality

See `docs/ai/ENGINEERING-QUALITY-REVIEW-2026-10-04.md`. PR #124 product validation completed with 305 tests passing; ANPOS repository-integrity also passed.

## REQ-90 — privacy/compliance

Technical minimization/storage controls are documented in `DATA_SOURCES.md`, data governance, R2 hashed-fingerprint architecture, workflow secret boundaries and the project threat model.

ANPOS does not self-certify jurisdiction-specific law. Qualified privacy/compliance review remains explicitly required before legal claims can be marked complete.

## REQ-91 / 93 / 94 / 95 / 96

Architecture decisions, compatibility/deprecation, runbooks/drills, hash-chained audit evidence and the unified risk register are implemented as project-specific machine state. Their final `passed` status is promoted only after the evidence package is merged and verified on an immutable main commit.
