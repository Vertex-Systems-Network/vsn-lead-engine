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
9. Default to one logical milestone per `continue` turn and avoid tight CI polling.
10. Before handoff, update compact state/checkpoint when the durable milestone or exact next action materially changes.

Compact limits:

- `CURRENT-STATE.yaml` <= 12 KiB
- `LAST-CHECKPOINT.md` <= 16 KiB

These files are a resume index only. GitHub, CI, R2 and live workbook evidence remain authoritative.
