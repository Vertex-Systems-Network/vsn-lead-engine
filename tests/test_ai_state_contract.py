import json
from pathlib import Path


STATE=Path(".ai/state/CURRENT-STATE.yaml")
CHECKPOINT=Path(".ai/state/LAST-CHECKPOINT.md")
RECOVERY=Path(".ai/state/RECOVERY-PROTOCOL.md")
AGENTS=Path("AGENTS.md")


def test_compact_ai_state_contract():
    assert STATE.exists()
    assert CHECKPOINT.exists()
    assert RECOVERY.exists()
    assert AGENTS.exists()

    assert STATE.stat().st_size <= 12 * 1024
    assert CHECKPOINT.stat().st_size <= 16 * 1024

    state=json.loads(STATE.read_text(encoding="utf-8"))
    assert state["project"]["repository"] == "Vertex-Systems-Network/vsn-lead-engine"
    assert len(state["observed_main_sha"]) == 40
    assert state["execution"]["active_task"]
    assert state["current_milestone"]
    assert state["milestone_status"]
    assert state["exact_next_safe_action"]
    assert state["production"]["daily_target"] == 12000
    assert state["production"]["accepted"] == 12000
    assert state["production"]["shortfall"] == 0


def test_checkpoint_and_recovery_have_required_resume_boundaries():
    checkpoint=CHECKPOINT.read_text(encoding="utf-8")
    for heading in ["## Verified","## Not Verified","## Known Risk","## Next Action"]:
        assert heading in checkpoint

    recovery=RECOVERY.read_text(encoding="utf-8")
    assert "CURRENT-STATE.yaml" in recovery
    assert "LAST-CHECKPOINT.md" in recovery
    assert "open GitHub Issues" in recovery
    assert "open PRs" in recovery
    assert "Never repeat" in recovery
    assert "Repository/runtime evidence outranks chat memory" in recovery


def test_agents_requires_compact_resume_first():
    agents=AGENTS.read_text(encoding="utf-8")
    state_pos=agents.index(".ai/state/CURRENT-STATE.yaml")
    checkpoint_pos=agents.index(".ai/state/LAST-CHECKPOINT.md")
    main_pos=agents.index("Resolve exact live protected/default")
    assert state_pos < checkpoint_pos < main_pos
    assert "OPEN GitHub Issues first" in agents
    assert "Do not replay completed mutations" in agents
    assert "reviewed immutable SHAs" in agents
