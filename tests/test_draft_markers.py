"""Draft bodies carry no status markers (contract, fake respond).

A proposed subject or body containing DRAFT, DO NOT SEND, NOT YET or
FOR REVIEW (case-insensitive) is refused in code: the app logs
draft_marker_refused with the marker found and asks the model to
re-issue the same message without status text. The gateway never stores
that version.
"""

from __future__ import annotations

import json

from app import gateway, runner
from app.store import append_event, create_job, list_events


def _seed():
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    append_event(job["id"], "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    return job["id"]


def _clean():
    return {"to": "Vestland Tekstil", "subject": "Confirm hold H-2041",
            "body": "Hello, please confirm hold H-2041.",
            "purpose": "order"}


def test_marker_in_subject_or_body_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    cases = [
        ("DRAFT: Confirm hold", "Hello, please confirm.", "DRAFT"),
        ("Confirm hold", "DRAFT - please confirm.", "DRAFT"),
        ("Confirm hold", "do not send yet, please confirm.", "DO NOT SEND"),
        ("For review: hold", "Hello.", "FOR REVIEW"),
        ("Hold", "Not yet confirmed, please hold.", "NOT YET"),
    ]
    for subject, body, want_marker in cases:
        job_id = _seed()
        args = {"to": "Vestland Tekstil", "subject": subject,
                "body": body, "purpose": "order"}
        outcome = gateway.check_propose_message(job_id, args, "01:10")
        assert outcome["ok"] is False
        assert outcome["marker"] == want_marker
        assert "re-issue" in outcome["reason"]
        kinds = [e["kind"] for e in list_events(job_id)]
        assert "draft" not in kinds
        refused = [e for e in list_events(job_id)
                   if e["kind"] == "draft_marker_refused"]
        assert len(refused) == 1
        assert refused[0]["payload"]["marker"] == want_marker


def test_clean_draft_still_stored(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    outcome = gateway.check_propose_message(job_id, _clean(), "01:10")
    assert outcome["ok"] is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "draft" in kinds
    assert "draft_marker_refused" not in kinds


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _message(text):
    return {"type": "message", "content": [
        {"type": "output_text", "text": text}]}


def _seed_answered():
    job = create_job(status="running", current_step="decision_turn",
                     virtual_time="21:30")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    runner.execute_tool_call(job_id, _call(
        "record_decision",
        {"outcome": "wake", "reason": "r", "evidence": []}, "c0"),
        "00:46")
    runner.execute_tool_call(job_id, _call("ask_owner", {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff 02:00", "what_checked": "all",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Bergen: the venue can receive it",
                    "No / not sure"]}, "ask-1"), "00:47")
    question_id = runner.question_event_id_of(job_id)
    ask = _call("ask_owner", {"question": "Q?"}, "ask-1")
    runner.save_checkpoint(job_id, [{"type": "message", "role": "user",
                                     "content": "hi"}, ask], question_id)
    runner.store_answer(job_id, "Bergen: the venue can receive it",
                        virtual_time="01:05")
    return job_id


def test_resume_reissues_without_marker_with_fake_respond(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()
    seen: dict = {}
    state = {"n": 0}

    def fake_respond(instructions, input_items, **kwargs):
        n = state["n"]
        state["n"] += 1
        if n == 0:
            return {"output": [_call("propose_message", {
                "to": "Vestland Tekstil",
                "subject": "DRAFT: Confirm hold H-2041",
                "body": "Hello, please confirm.",
                "purpose": "order"}, "c1")], "text": ""}
        if n == 1:
            seen["second_input"] = input_items
            return {"output": [_call("propose_message", {
                "to": "Vestland Tekstil",
                "subject": "Confirm hold H-2041",
                "body": "Hello, please confirm.",
                "purpose": "order"}, "c2")], "text": ""}
        return {"output": [_message("done")], "text": "done"}

    summary = runner.resume_job(job_id, respond_fn=fake_respond)
    assert summary["status"] == "done"
    refused = [e for e in list_events(job_id)
               if e["kind"] == "draft_marker_refused"]
    assert len(refused) == 1
    assert refused[0]["payload"]["marker"] == "DRAFT"
    drafts = [e for e in list_events(job_id) if e["kind"] == "draft"]
    assert len(drafts) == 1
    assert drafts[0]["payload"]["subject"] == "Confirm hold H-2041"
    assert "DRAFT" not in drafts[0]["payload"]["subject"]
    assert "re-issue" in json.dumps(seen["second_input"])


def test_resume_instructions_state_attribution_and_clean_body():
    job = {"id": "unused-for-text"}
    answer = {"id": 1, "payload": {"choice": "x"}}
    text = runner.build_resume_instructions(job["id"], answer,
                                            "supervision")
    assert "Say who confirmed what" in text
    assert "has confirmed nothing unless a source from that party says so" \
        in text
    assert "the owner's answer is the owner's answer" in text
    assert "exactly as they would be sent" in text
    assert "DRAFT" in runner.PROPOSE_MESSAGE_TOOL["description"]
    assert "exactly the text that would be sent" in \
        runner.PROPOSE_MESSAGE_TOOL["description"]
