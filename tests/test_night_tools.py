"""Day 3 step E part 1 (pure code, no model).

Every night turn offers the same six tools; a namespaced tool name such as
``default.submit_hold`` is normalised before dispatch and logged; run_check
calls from the read turn are stored but never satisfy the post-00:38 gate.
"""

from __future__ import annotations

import json

from app import runner
from app.store import append_event, create_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"

NIGHT_NAMES = {
    "record_claim", "run_check", "record_decision",
    "ask_owner", "submit_hold", "propose_message",
}


def _call(name, args, call_id="c1"):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def _tool_names(tools):
    return {t["name"] for t in tools}


def _seed_hold_job(answer_vt="01:05"):
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:47", "question",
                 {"question": "Can the venue receive Wed 08-12?",
                  "why_now": "cutoff near", "what_checked": "sources",
                  "if_yes": "hold", "if_no": "no hold",
                  "options": ["Bergen: the venue can receive it",
                              "No / not sure"]})
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


def test_every_night_turn_offers_the_same_six_tools():
    assert _tool_names(runner.READ_TOOLS) == NIGHT_NAMES
    assert _tool_names(runner.REASSESS_TOOLS) == NIGHT_NAMES
    assert _tool_names(runner.DECISION_TOOLS) == NIGHT_NAMES


def test_namespaced_submit_hold_is_normalised_and_dispatched(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, hold_args = _seed_hold_job()
    out = runner.execute_tool_call(
        job_id, _call("default.submit_hold", hold_args), "01:06")
    assert json.loads(out["output"]).get("ok") is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "effect" in kinds
    normalised = [e for e in list_events(job_id)
                  if e["kind"] == "tool_name_normalised"]
    assert len(normalised) == 1
    assert normalised[0]["payload"]["requested"] == "default.submit_hold"
    assert normalised[0]["payload"]["normalised"] == "submit_hold"


def test_unknown_name_after_normalisation_is_still_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="22:30")
    out = runner.execute_tool_call(
        job["id"], _call("default.no_such_tool", {}), "22:30")
    assert "unknown tool" in out["output"]
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert "tool_refused" in kinds
    assert "tool_name_normalised" in kinds


def test_resume_turn_normalises_namespaced_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, hold_args = _seed_hold_job()
    out = runner.execute_resume_tool_call(
        job_id, _call("default.submit_hold", hold_args, "c9"), "01:06")
    assert json.loads(out["output"]).get("ok") is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "tool_name_normalised" in kinds
    assert "effect" in kinds


def test_namespaced_hold_counts_for_act_consistency(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, hold_args = _seed_hold_job()
    state = {"n": 0}
    script = [
        {"output": [_call("record_decision",
                          {"outcome": "act_under_permission", "reason": "r",
                           "evidence": []}, "c1")], "text": ""},
        {"output": [_call("default.submit_hold", hold_args, "c2")],
         "text": ""},
        {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "held"}]}],
         "text": "held"},
    ]

    def stub(instructions, input_items, **kwargs):
        item = script[state["n"]]
        state["n"] += 1
        return item

    summary = runner.run_turn(job_id, "instructions", [{"t": 0}],
                              runner.REASSESS_TOOLS, stub, "01:06")
    assert summary["status"] == "complete"
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "nudge" not in kinds
    assert "effect" in kinds


def test_read_turn_checks_do_not_satisfy_the_post_event_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="22:30")
    job_id = job["id"]
    for name in runner.CHECK_NAMES:
        out = runner.execute_tool_call(
            job_id, _call("run_check", {"name": name, "result": "fail",
                                        "evidence": [], "note": "read turn"},
                          call_id=f"check-{name}"), "22:30")
        assert json.loads(out["output"]).get("stored") is True
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    runner.execute_tool_call(
        job_id, _call("record_decision",
                      {"outcome": "wake", "reason": "r", "evidence": []},
                      call_id="c-dec"), "00:46")
    out = runner.execute_tool_call(
        job_id, _call("ask_owner",
                      {"question": "Q?", "why_now": "w", "what_checked": "c",
                       "if_yes": "y", "if_no": "n", "options": ["A", "B"]},
                      call_id="c-ask"), "00:47")
    payload = json.loads(out["output"])
    assert "refused" in payload["error"]
    assert any("run_check" in missing for missing in payload["missing"])
