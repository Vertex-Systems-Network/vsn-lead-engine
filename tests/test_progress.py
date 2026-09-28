import json

from vsn_lead_engine.progress import emit_progress


def test_emit_progress_outputs_compact_json(capsys):
    payload=emit_progress(
        "source_search_start",
        category="Cars",
        city="Austin",
        candidate_partition=3,
    )
    line=capsys.readouterr().out.strip()
    decoded=json.loads(line)

    assert payload is not None
    assert decoded["vsn_progress"]==1
    assert decoded["event"]=="source_search_start"
    assert decoded["category"]=="Cars"
    assert decoded["city"]=="Austin"
    assert decoded["candidate_partition"]==3
    assert "timestamp" in decoded


def test_emit_progress_can_be_disabled(capsys):
    payload=emit_progress("event_start",enabled=False)
    assert payload is None
    assert capsys.readouterr().out==""
