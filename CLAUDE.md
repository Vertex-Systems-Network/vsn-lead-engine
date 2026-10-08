# Claude Code Adapter

Read `AGENTS.md` first, then `.ai/manifest.json`. Determine your active role and load only the common + role-specific protocol files listed there.

Repository/Git state is authoritative over conversational assumptions. Do not bypass consent, quality, security, Supervisor fencing, Worker claim, or GitHub governance rules. If acting as a Worker, follow `AUTO-AGENT.md`; if acting as Supervisor, follow `SUPERVISOR.md` and `ORCHESTRATOR.md`.

For an authorized `continue`/resume, follow the full ready-frontier loop in `AGENTS.md` and `.ai/state/RECOVERY-PROTOCOL.md`: do not stop after one milestone, and do not ask the owner to choose technical next steps or fix routine errors. Update README progress/status in the same material-development PR and checkpoint real CI/merge evidence. A persistent distributed Supervisor cannot be claimed without runtime identity and lease; otherwise continue safe authenticated single-session work within the host invocation budget.
