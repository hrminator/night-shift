"""Consistency nudges (pure code, no model): wake needs ask_owner, act needs submit_hold.

Each rule fires at most once per turn as a `nudge` event with the exact user
message; a turn that still ends inconsistently is marked step_failed.
"""

from __future__ import annotations

import json

from app import runner
from app.store import append_event, create_job, get_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
WAKE_MSG = "You recorded wake but asked nothing. Either call ask_owner now or record a different decision."
ACT_MSG = "You recorded act_under_permission but placed no hold. Either call submit_hold now or record a different decision."


def _call(name, args, call_id):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def _text(words):
    return {
        "type": "message",
        "content": [{"type": "output_text", "text": words}],
    }


def _ask_args():
    return {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff 02:00",
        "what_checked": "all sources",
        "if_yes": "hold",
        "if_no": "no hold",
        "options": ["Bergen: the venue can receive it", "No / not sure"],
    }


def _seed_hold_job(answer_vt="01:05"):
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    answer = append_event(job_id, answer_vt, "owner_answer",
                          {"choice": "Bergen: the venue can receive it",
                           "source": "owner"})
    hold_args = {
        "portal": "vestland_portal",
        "action": "capacity_hold",
        "product": "100 tote bags with logo",
        "quantity": 100,
        "print_file": "fjord-fern-logo-print.pdf",
        "address": VENUE_ADDRESS,
        "delivery_window": "Wed Nov 11 08:00-12:00",
        "ordering_contact": "Kari Strandli, studio coordinator, orders@fjord-fern.example.com, +47 22 00 11 22",
        "recipient_can_receive": True,
        "cost": 0,
        "binding": False,
        "hold_ends": "09:00",
        "sources": {
            "recipient_can_receive": {"kind": "owner_answer",
                                      "id": answer["id"]},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"},
        },
    }
    return job_id, hold_args


def _decision_args(outcome):
    return {"outcome": outcome, "reason": "r", "evidence": []}


def _run(job_id, script, tools, virtual_time="00:39"):
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        item = script[state["n"]]
        state["n"] += 1
        return item

    return runner.run_turn(job_id, "instructions", [{"t": 0}], tools, stub,
                           virtual_time), state


def test_wake_without_ask_nudged_once_then_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    job_id = job["id"]
    script = [
        {"output": [_call("record_decision", _decision_args("wake"), "c1")],
         "text": ""},
        {"output": [_text("all done")], "text": "all done"},
        {"output": [_call("ask_owner", _ask_args(), "c2")], "text": ""},
        {"output": [_text("done")], "text": "done"},
    ]
    summary, _ = _run(job_id, script, runner.REASSESS_TOOLS)
    assert summary["status"] == "complete"
    kinds = [e["kind"] for e in list_events(job_id)]
    assert kinds.count("nudge") == 1
    nudge = next(e for e in list_events(job_id) if e["kind"] == "nudge")
    assert nudge["payload"]["rule"] == "wake_without_ask"
    assert nudge["payload"]["message"] == WAKE_MSG
    assert "question" in kinds


def test_wake_without_ask_still_inconsistent_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    job_id = job["id"]
    script = [
        {"output": [_call("record_decision", _decision_args("wake"), "c1")],
         "text": ""},
        {"output": [_text("all done")], "text": "all done"},
        {"output": [_text("still done")], "text": "still done"},
    ]
    summary, _ = _run(job_id, script, runner.REASSESS_TOOLS)
    assert summary["status"] == "failed"
    events = list_events(job_id)
    assert sum(1 for e in events if e["kind"] == "nudge") == 1
    assert "step_failed" in [e["kind"] for e in events]
    assert get_job(job_id)["status"] == "failed"


def test_act_with_hold_needs_no_nudge(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, hold_args = _seed_hold_job()
    script = [
        {"output": [_call("record_decision",
                          _decision_args("act_under_permission"), "c1")],
         "text": ""},
        {"output": [_call("submit_hold", hold_args, "c2")], "text": ""},
        {"output": [_text("held")], "text": "held"},
    ]
    summary, _ = _run(job_id, script, runner.REASSESS_TOOLS,
                       virtual_time="01:06")
    assert summary["status"] == "complete"
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "nudge" not in kinds
    assert "effect" in kinds


def test_act_without_hold_nudged_once_then_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    job_id = job["id"]
    script = [
        {"output": [_call("record_decision",
                          _decision_args("act_under_permission"), "c1")],
         "text": ""},
        {"output": [_text("all done")], "text": "all done"},
        {"output": [_text("still done")], "text": "still done"},
    ]
    summary, _ = _run(job_id, script, runner.REASSESS_TOOLS)
    assert summary["status"] == "failed"
    events = list_events(job_id)
    nudges = [e for e in events if e["kind"] == "nudge"]
    assert len(nudges) == 1
    assert nudges[0]["payload"]["rule"] == "act_without_hold"
    assert nudges[0]["payload"]["message"] == ACT_MSG
    assert "step_failed" in [e["kind"] for e in events]
