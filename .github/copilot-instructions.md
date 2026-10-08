# GitHub Copilot Repository Instructions

Read `AGENTS.md` and `.ai/manifest.json` first. Infer the active role from the user's request and repository state, then load the manifest's common + role-specific files instead of blindly loading every protocol document.

GitHub repository reality is authoritative. Never bypass atomic Worker claim ownership, current Supervisor fencing token, explicit consent gates, required CI/security checks, or repository governance. Use `AUTO-AGENT.md` for Worker mode and `SUPERVISOR.md` + `ORCHESTRATOR.md` for Supervisor mode.

For an authorized `continue`/resume, follow the full ready-frontier loop in `AGENTS.md` and `.ai/state/RECOVERY-PROTOCOL.md`: do not stop after one milestone, and do not ask the owner to choose technical next steps or fix routine errors. Update README progress/status in the same material-development PR and checkpoint real CI/merge evidence. A persistent distributed Supervisor cannot be claimed without runtime identity and lease; otherwise continue safe authenticated single-session work within the host invocation budget.
