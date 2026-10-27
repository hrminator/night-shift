"""Runner tests (pure code): ask_owner gating, malformed tools, checkpoint."""

from __future__ import annotations

import json

from app import runner
from app.store import append_event, create_job, get_job, list_events


def _call(name, args, call_id="c1"):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def test_ask_owner_refused_without_wake(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    job = create_job(virtual_time="00:38")
    out = runner.execute_tool_call(
        job["id"],
        _call("ask_owner", {
            "question": "Q?", "why_now": "w", "what_checked": "c",
            "if_yes": "y", "if_no": "n", "options": ["A", "B"],
        }),
    )
    assert "refused" in out["output"]
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert "question" not in kinds
    assert "tool_refused" in kinds


def test_wake_then_ask_owner_allowed_and_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    job = create_job(virtual_time="00:38")
    claim_out = runner.execute_tool_call(
        job["id"],
        _call("record_claim", {"source": "portal", "quote": "van 08-12"}),
    )
    claim_id = json.loads(claim_out["output"])["claim_id"]
    runner.execute_tool_call(
        job["id"],
        _call("record_decision", {
            "outcome": "wake", "reason": "last verified route",
            "evidence": [claim_id],
        }, call_id="c2"),
    )
    out = runner.execute_tool_call(
        job["id"],
        _call("ask_owner", {
            "question": "Can the venue receive Wed 08-12?",
            "why_now": "cutoff 02:00", "what_checked": "all sources",
            "if_yes": "hold", "if_no": "no hold",
            "options": ["Bergen: the venue can receive it", "No / not sure"],
        }, call_id="c3"),
    )
    question_id = json.loads(out["output"])["question_id"]
    checkpoint = runner.save_checkpoint(job["id"], [{"t": 1}], question_id)
    assert checkpoint["kind"] == "checkpoint"
    stored = get_job(job["id"])
    assert stored["status"] == "waiting_for_owner"
    assert stored["pending_question_id"] == question_id


def test_malformed_tool_call_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    job = create_job(virtual_time="00:38")
    out = runner.execute_tool_call(
        job["id"], _call("record_decision", {"outcome": "maybe"}, call_id="c9")
    )
    assert "error" in out["output"]
    assert list_events(job["id"])[-1]["kind"] == "tool_malformed"


def test_plain_text_twice_marks_step_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    job = create_job(virtual_time="00:38")
    append_event(job["id"], "00:38", "revised_quote", {"quote": "Q-1187-B"})

    def silent(_instructions, _input, **_kwargs):
        return {"output": [{"type": "message",
                            "content": [{"type": "output_text",
                                         "text": "all fine"}]}], "text": "all fine"}

    summary = runner.run_decision_turn(
        job["id"], respond_fn=silent,
        original_file_id="f1", revised_file_id="f2",
    )
    assert summary["status"] == "failed"
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert "step_failed" in kinds
    assert get_job(job["id"])["status"] == "failed"
