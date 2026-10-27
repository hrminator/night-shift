"""Contract tests 8, 9, 10 (pure code, no model).

8: the spend cap holds with several calls in flight (fake respond plus
threads). 9: a turn with no tool call, or too many, is handled and logged.
10: a tool call failing the schema is refused, logged as malformed, and
never reaches the gateway.
"""

from __future__ import annotations

import json
import threading
import time

from app import runner
from app.spend import SpendCap, call_with_cap, cost_usd
from app.store import append_event, create_job, list_events


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _text(words):
    return {"type": "message", "content": [
        {"type": "output_text", "text": words}]}


def _fake_respond_factory(dialled):
    def fake(instructions, input_items, **kwargs):
        dialled.append(1)
        time.sleep(0.01)
        return {"output": [_text("ok")], "text": "ok",
                "usage": {"input_tokens": 8000, "output_tokens": 1000,
                          "input_tokens_details": {"cached_tokens": 0}}}
    return fake


def test_spend_cap_holds_with_calls_in_flight(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    actual = cost_usd(8000, 0, 1000)
    cap = SpendCap(0.05)
    dialled: list = []
    fake = _fake_respond_factory(dialled)
    errors: list = []

    def worker():
        try:
            for _ in range(5):
                call_with_cap(fake, cap, 0.02, "instr", [{"t": 1}])
        except Exception as exc:  # noqa: BLE001 - threads must not die silent
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors
    assert cap.spent_usd <= 0.05
    assert cap.refusals >= 1
    assert len(dialled) * actual == cap.spent_usd


def test_turn_with_no_tool_call_handled_and_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")

    def silent(instructions, input_items, **kwargs):
        return {"output": [_text("just thinking")], "text": "just thinking"}

    summary = runner.run_turn(job["id"], "instructions", [{"t": 0}],
                              runner.REASSESS_TOOLS, silent, "00:39",
                              max_model_calls=2)
    assert summary["status"] == "failed"
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert "model_plain_text" in kinds
    assert "step_failed" in kinds


def test_turn_with_too_many_tool_calls_truncated_and_logged(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    calls = [_call("record_claim", {"source": f"s{i}", "quote": f"q{i}"},
                   f"c{i}") for i in range(20)]
    script = [{"output": calls, "text": ""},
              {"output": [_text("done")], "text": "done"}]
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        item = script[state["n"]]
        state["n"] += 1
        return item

    summary = runner.run_turn(job["id"], "instructions", [{"t": 0}],
                              runner.REASSESS_TOOLS, stub, "00:39")
    assert summary["status"] == "complete"
    events = list_events(job["id"])
    limits = [e for e in events if e["kind"] == "tool_limit"]
    assert limits and limits[0]["payload"]["kept"] == 16
    assert sum(1 for e in events if e["kind"] == "claim") == 16


def _authorized_job():
    job = create_job(status="running", current_step="resuming",
                     virtual_time="01:05")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "01:05", "owner_answer",
                 {"choice": "yes", "source": "owner"})
    return job_id


def test_malformed_submit_hold_never_reaches_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _authorized_job()
    out = runner.execute_tool_call(
        job_id, _call("submit_hold", {"portal": 1}, "c1"), "01:05")
    assert "schema" in out["output"]
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "tool_malformed" in kinds
    assert "gateway_check" not in kinds
    assert "permission_used" not in kinds
    assert "effect" not in kinds


def test_malformed_checks_and_drafts_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _authorized_job()
    bad_check = runner.execute_tool_call(
        job_id, _call("run_check", {"name": "nope", "result": "fail",
                                    "evidence": [], "note": "x"}, "c2"),
        "00:39")
    assert "error" in bad_check["output"]
    bad_draft = runner.execute_tool_call(
        job_id, _call("propose_message",
                       {"to": "o", "subject": "s", "purpose": "p"}, "c3"),
        "01:05", )
    assert "error" in bad_draft["output"]
    kinds = [e["kind"] for e in list_events(job_id)]
    assert kinds.count("tool_malformed") == 2
    assert "gateway_check" not in kinds
