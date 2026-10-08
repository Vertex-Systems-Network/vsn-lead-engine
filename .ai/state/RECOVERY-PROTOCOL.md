# Recovery Protocol

Use this on every fresh supervisor session, `continue`/resume, interruption, connector failure, or message-delivery timeout.

1. Read `.ai/state/CURRENT-STATE.yaml` and `.ai/state/LAST-CHECKPOINT.md` first.
2. Resolve the exact current default/protected `main` SHA.
3. Treat `observed_main_sha` as a snapshot-basis anchor, not as authority over newer live evidence.
4. Reconcile all open GitHub Issues, then all open PRs, before starting new work.
5. Inspect commits since the snapshot anchor when live main has advanced.
6. Repository/runtime evidence outranks chat memory and this compact index.
7. Never repeat a branch/file/PR/merge/production trigger/destructive action merely because a previous response was missing or timed out.
8. If evidence conflicts, record the conflict and stop only the affected mutation; continue safe independent work when possible.
9. Continue across the full ready, authorized dependency frontier within the current host invocation. A milestone completion is a checkpoint, not a stop condition: immediately reconcile newly unblocked work, fix recoverable errors within budgets and proceed without technical owner confirmation. Never infer 24/7 execution from a repository document; when the host ends, retain a resumable checkpoint instead.
10. If one work unit is blocked by CI, a missing tool, verified external consent or a circuit breaker, record exact evidence, isolate it and continue independent authorized work. Do not attempt forbidden bypasses, unbounded retries or repeated CI polling.
11. Update README milestone bars/status and machine/checkpoint state in the same feature PR or reconciliation PR. Verify current protected `main` README after each merge; a status change is incomplete until its durable mirror is reconciled.
12. Before handoff, update compact state/checkpoint with exact Git/CI evidence, current safety gates and the next ready frontier when the durable milestone or exact next action materially changes.

Compact limits:

- `CURRENT-STATE.yaml` <= 12 KiB
- `LAST-CHECKPOINT.md` <= 16 KiB

These files are a resume index only. GitHub, CI, R2 and live workbook evidence remain authoritative.
