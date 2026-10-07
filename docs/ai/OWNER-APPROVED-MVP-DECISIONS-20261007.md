# Owner-approved SaaS MVP decisions

Decision date: 2026-10-07 (Asia/Karachi)
Repository: Vertex-Systems-Network/vsn-lead-engine
Authority: explicit owner instruction in the active development session: “tu us ko solve krro or start krro”

These decisions resolve the previously blocked product-boundary gate for design work. They do not approve a production stack, paid provider, billing account, legal conclusion, or launch.

## Approved MVP boundary

- Product sequence: responsive web-first SaaS over versioned shared contracts; desktop and mobile remain later clients.
- Initial market scope: United States and Canada, inherited from the current engine, while SaaS demand remains subject to validation.
- Core user workflow: workspace -> target-market/search configuration -> manual or daily scheduled job -> job history/status -> provenance-aware lead results -> filters -> guarded export.
- Initial lead quality invariant: phone-qualified accepted leads remain required; existing taxonomy and exact dedupe rules are not weakened.
- Source model: free-first and source-policy-gated. No paid discovery API, adapter, scraping bypass, or provider-key exposure is approved by this decision.
- Commercial model: plans and usage entitlements are contract concepts only. No payment gateway, price, subscription billing, or customer charge is enabled.
- AI scope: bounded search-configuration assistance and explanations with explicit user confirmation before execution or paid action. No autonomous spending, outreach, unrestricted scraping, or unrestricted code execution.
- Production boundary: the existing daily collector, scheduler, Google Sheets delivery, R2 authority, and P01-P70 runtime remain unchanged.

## Success criteria for the design/MVP gates

1. A tenant cannot read or mutate another tenant’s workspaces, jobs, leads, exports, credentials, usage, or AI context.
2. Every job has explicit lifecycle, idempotency, retry, pause/cancel, timezone/DST and failure semantics.
3. Every lead result retains source/provenance/freshness and deletion/retention behavior.
4. Usage and cost limits fail closed before work is dispatched.
5. Source adapters require an allowlisted policy with rights, fields, retention, rate and cost metadata.
6. Public claims distinguish implemented behavior, planned behavior, and unvalidated hypotheses.
7. Web accessibility target is WCAG 2.2 AA with reduced-motion support.
8. No SaaS runtime is deployed until the system design, threat model, technology stack, provider rights and required external reviews are separately evidenced.

## Explicitly unresolved gates

- External user interviews and task tests.
- Source-specific legal/rights and coverage/yield review.
- System/threat-model review.
- Technology stack, hosting, database, queue, AI provider and payment approval.
- Qualified privacy/compliance review.
- Production launch and billing approval.

This file is an owner decision record for advancing design work, not evidence that the unresolved gates have passed.
