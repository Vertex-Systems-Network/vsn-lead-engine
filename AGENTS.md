# VSN Lead Engine Supervisor Contract

For every fresh development session, `continue`, resume, or timeout recovery:

1. Read `.ai/state/CURRENT-STATE.yaml`.
2. Read `.ai/state/LAST-CHECKPOINT.md`.
3. Resolve exact live protected/default `main`.
4. Reconcile OPEN GitHub Issues first, then OPEN PRs.
5. Prefer live repository/runtime evidence over chat memory.
6. Execute one bounded logical milestone by default.
7. Do not replay completed mutations after a timeout without proving they did not happen.
8. Avoid tight CI polling; refresh at meaningful boundaries.
9. Keep README status synchronized when a durable milestone changes.
10. End with repo name, completed milestone, next safe action, module progress, and overall operational status.

Security and correctness rules:

- preserve phone-only accepted-lead semantics;
- preserve exact R2 cross-day dedupe authority;
- preserve US + Canada scope unless explicitly changed;
- preserve 1,000 accepted unique leads/category/day target;
- never weaken taxonomy precision merely to fill quota;
- do not add paid discovery dependencies without explicit approval;
- keep GitHub Actions dependencies on reviewed immutable SHAs.
