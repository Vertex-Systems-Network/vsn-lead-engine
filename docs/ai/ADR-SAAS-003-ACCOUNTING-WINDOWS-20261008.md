# Explicit accounting windows without billing activation

Accepted development contract, 2026-10-08 PKT. Applies to M5 foundation/billing accounting; preserves the current Django/PostgreSQL and Next stack.

Choose nullable, explicit workspace accounting periods alongside the existing current usage counter. Preserve period-null cumulative data and refuse initial conversion when historical settled totals are nonzero. Archive prior settled totals transactionally before a safe reset; reservations retain their original period. Rollover is internal/manual and requires no unresolved capacity. Automatic calendar/payment-driven reset is deferred until authoritative billing-event and operations contracts exist.

This avoids treating an expired clock/window as proof that external work had no effect. Started/unknown jobs block rollover; verified late receipts settle the original period, and replay cannot charge the new period. Pending intents end at the configured period boundary. Current role/entitlement checks and the shared workspace lock serialize all reservations, claims, receipt settlement and rollover.

Alternatives: keep cumulative usage forever (fails future subscription-period needs); reset counters on a date with outstanding work (unsafe accounting); introduce a payment vendor now (unnecessary external commitment). The additive internal window is a reversible development default, not an activated subscription product. Empty migrations reverse; populated history requires reviewed preservation/roll-forward, not destructive reversal. Production migration requires backups and explicit legacy history treatment.

The usage response adds `period={id, starts_at, ends_at}` and `accounting=period_development` only for configured windows. `reset_at` remains null: no automatic reset is promised. Django and Next consumers are updated together; legacy mode remains supported. Windows are trusted server configuration, not client-authoritative paid entitlement.

Tests cover key replay/conflict, window/role validation, expired dispatch denial, legacy preservation, unresolved reservation/unknown-job blocking, late receipt and new-period isolation, atomic failure/reverse guard and PostgreSQL duplicate-start/rollover-reservation races. HTTP smoke verifies real Next rendering of configured window metadata. Browser/customer/payment/release acceptance remains open.
