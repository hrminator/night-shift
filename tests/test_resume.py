"""Resume tests (pure code): answer storage, stub-model resume, morning page."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.main as main_mod
from app import runner
from app.store import append_event, create_job, get_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"


def _call(name, args, call_id):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def _message(text):
    return {
        "type": "message",
        "content": [{"type": "output_text", "text": text}],
    }


def _seed_answered(answer_vt="01:05"):
    job = create_job(status="running", current_step="decision_turn",
                     virtual_time="21:30")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    ask = _call("ask_owner", {"question": "Q?"}, "ask-1")
    runner.execute_tool_call(job_id, _call(
        "record_decision",
        {"outcome": "wake", "reason": "r", "evidence": []}, "c0"),
        "00:46")
    runner.execute_tool_call(job_id, {
        "type": "function_call", "call_id": "ask-1", "name": "ask_owner",
        "arguments": json.dumps({
            "question": "Can the venue receive Wed 08-12?",
            "why_now": "cutoff 02:00", "what_checked": "all",
            "if_yes": "hold", "if_no": "no hold",
            "options": ["Bergen: the venue can receive it", "No / not sure"]})},
        "00:47")
    question_id = runner.question_event_id_of(job_id)
    runner.save_checkpoint(job_id, [{"type": "message", "role": "user",
                                     "content": "hi"}, ask], question_id)
    runner.store_answer(job_id, "Bergen: the venue can receive it",
                        virtual_time=answer_vt)
    return job_id


def _valid_hold_args(answer_id: int) -> dict:
    return {
        "portal": "Vestland Tekstil",
        "fields": {
            "product": "100 tote bags with logo",
            "quantity": 100,
            "print_file": "logo.pdf",
            "address": VENUE_ADDRESS,
            "delivery_window": "Wed Nov 11 08:00-12:00",
            "ordering_contact": "owner",
            "recipient_can_receive": "yes",
            "cost": 0,
            "binding": False,
            "hold_ends": "09:00",
            "sources": {
                "recipient_can_receive": answer_id,
                "route": "vestland_portal.json v1",
                "window": "vestland_portal.json v1",
            },
        },
    }


def _resume_stub(job_id: str):
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        answers = [e for e in list_events(job_id)
                   if e["kind"] == "owner_answer"]
        aid = answers[-1]["id"]
        n = state["n"]
        state["n"] += 1
        if n == 0:
            return {"output": [_call("submit_hold", _valid_hold_args(aid),
                                     "s1")], "text": ""}
        if 1 <= n <= 3:
            return {"output": [_call(
                "propose_message",
                {"to": f"Recipient {n}", "subject": f"Subject {n}",
                 "body": f"Exact body {n}", "purpose": f"purpose {n}"},
                f"p{n}")], "text": ""}
        return {"output": [_message("night complete")],
                "text": "night complete"}

    return stub


def test_store_answer_defaults_to_0105(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:47")
    event = runner.store_answer(job["id"], "Bergen: the venue can receive it")
    assert event["kind"] == "owner_answer"
    assert event["virtual_time"] == "01:05"
    assert event["payload"]["source"] == "owner"
    assert get_job(job["id"])["status"] == "answered"


def test_store_answer_virtual_time_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:47")
    event = runner.store_answer(job["id"], "No / not sure",
                                virtual_time="01:20")
    assert event["virtual_time"] == "01:20"


def test_resume_places_hold_and_three_drafts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()
    summary = runner.resume_job(job_id, respond_fn=_resume_stub(job_id))
    assert summary["status"] == "done"
    kinds = [e["kind"] for e in list_events(job_id)]
    for kind in ("owner_answer", "permission_used", "gateway_result",
                 "effect"):
        assert kind in kinds
    effects = [e for e in list_events(job_id) if e["kind"] == "effect"]
    assert len(effects) == 1
    assert "H-2041" in effects[0]["payload"]["acknowledgement"]
    drafts = [e for e in list_events(job_id)
              if e["kind"] == "draft"
              and e["payload"].get("purpose") != "hold_request"]
    assert len(drafts) == 3
    assert all(d["payload"]["status"] == "awaiting_approval" for d in drafts)
    stored = get_job(job_id)
    assert stored["status"] == "done"
    assert stored["virtual_time"] == "07:00"


def test_resume_refused_without_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="waiting_for_owner", virtual_time="00:47")
    summary = runner.resume_job(job["id"], respond_fn=_resume_stub(job["id"]))
    assert summary["status"] == "refused"


def test_resume_silent_model_fails_without_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()

    def silent(instructions, input_items, **kwargs):
        return {"output": [_message("all fine")], "text": "all fine"}

    summary = runner.resume_job(job_id, respond_fn=silent)
    assert summary["status"] == "failed"
    assert "effect" not in [e["kind"] for e in list_events(job_id)]


def test_morning_page_renders_label_ack_drafts_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()
    runner.resume_job(job_id, respond_fn=_resume_stub(job_id))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get(f"/jobs/{job_id}/morning")
    assert response.status_code == 200
    body = response.text
    assert "Vestland slot held until 09:00" in body
    assert "H-2041" in body
    assert "Simulated supplier system" in body
    assert "Exact body 1" in body
    assert "Approve this exact text" in body
    assert "permission" in body and "once-only" in body


def test_approve_stub_records_event(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()
    runner.resume_job(job_id, respond_fn=_resume_stub(job_id))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        f"/jobs/{job_id}/approve",
        content="draft_id=3",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "approval_requested" in kinds


def test_answer_endpoint_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="waiting_for_owner", virtual_time="00:47")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        f"/jobs/{job['id']}/answer",
        content="choice=Bergen%3A+the+venue+can+receive+it",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    events = list_events(job["id"])
    assert events[-1]["kind"] == "owner_answer"
    assert events[-1]["virtual_time"] == "01:05"
    job2 = create_job(status="waiting_for_owner", virtual_time="00:47")
    response = client.post(
        f"/jobs/{job2['id']}/answer",
        content="choice=No&virtual_time=01%3A20",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert list_events(job2["id"])[-1]["virtual_time"] == "01:20"
