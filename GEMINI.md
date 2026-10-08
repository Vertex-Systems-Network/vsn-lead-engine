# Gemini Adapter

Read `AGENTS.md` and `.ai/manifest.json` before acting. Select the active role and load only the manifest's common + role files.

Treat repository/Git/tests as source of truth. Respect technology/scope consent, atomic Worker claims, Supervisor fencing, quality/security gates, and GitHub governance. Worker mode follows `AUTO-AGENT.md`; Supervisor mode follows `SUPERVISOR.md` + `ORCHESTRATOR.md`.

For an authorized `continue`/resume, follow the full ready-frontier loop in `AGENTS.md` and `.ai/state/RECOVERY-PROTOCOL.md`: do not stop after one milestone, and do not ask the owner to choose technical next steps or fix routine errors. Update README progress/status in the same material-development PR and checkpoint real CI/merge evidence. A persistent distributed Supervisor cannot be claimed without runtime identity and lease; otherwise continue safe authenticated single-session work within the host invocation budget.
