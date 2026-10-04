# GitHub Copilot Repository Instructions

Read `AGENTS.md` and `.ai/manifest.json` first. Infer the active role from the user's request and repository state, then load the manifest's common + role-specific files instead of blindly loading every protocol document.

GitHub repository reality is authoritative. Never bypass atomic Worker claim ownership, current Supervisor fencing token, explicit consent gates, required CI/security checks, or repository governance. Use `AUTO-AGENT.md` for Worker mode and `SUPERVISOR.md` + `ORCHESTRATOR.md` for Supervisor mode.
