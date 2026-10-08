# ANPOS Repository Rule

Read `AGENTS.md` then `.ai/manifest.json`. Resolve the current role and use only common + role-specific protocol files. Treat GitHub/Git/tests as authoritative. Respect atomic Worker claims, Supervisor fencing, explicit consent, required quality/security gates, and repository governance. Worker mode uses `AUTO-AGENT.md`; Supervisor mode uses `SUPERVISOR.md` and `ORCHESTRATOR.md`.

For an authorized `continue`/resume, follow the full ready-frontier loop in `AGENTS.md` and `.ai/state/RECOVERY-PROTOCOL.md`: do not stop after one milestone, and do not ask the owner to choose technical next steps or fix routine errors. Update README progress/status in the same material-development PR and checkpoint real CI/merge evidence. A persistent distributed Supervisor cannot be claimed without runtime identity and lease; otherwise continue safe authenticated single-session work within the host invocation budget.
