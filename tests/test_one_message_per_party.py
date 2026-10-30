"""One current message per party (contract, fake respond).

A second draft to the same recipient in the same turn with a different
purpose is refused in code: the app logs duplicate_recipient_refused
with the recipient and both purposes and asks the model to fold the new
content into one message by re-issuing the existing purpose, or drop it.
The gateway never stores the refused version. A later-turn draft to the
same recipient supersedes the earlier one, so the morning counts one.
"""

from __future__ import annotations

import json
import re

from app import gateway, runner
from app.main import render_morning_page
from app.store import append_event, create_job, list_events

R = "supplier-a@example.com"
S = "supplier-b@example.com"


def _seed():
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    append_event(job["id"], "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    return job["id"]


def _args(to, purpose, body):
    return {"to": to, "subject": f"Subject for {purpose}",
            "body": body, "purpose": purpose}


def test_two_recipients_same_turn_not_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    first = gateway.check_propose_message(
        job_id, _args(R, "purpose_a", "Hello A, first message."), "01:05")
    second = gateway.check_propose_message(
        job_id, _args(S, "purpose_b", "Hello B, other message."), "01:05")
    assert first["ok"] is True
    assert second["ok"] is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "duplicate_recipient_refused" not in kinds
    assert len([e for e in list_events(job_id)
                if e["kind"] == "draft"]) == 2


def test_later_turn_same_recipient_supersedes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    early = gateway.check_propose_message(
        job_id, _args(R, "purpose_a", "Hello A, early plan."), "22:30")
    assert early["ok"] is True
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    late = gateway.check_propose_message(
        job_id, _args(R, "purpose_b", "Hello A, current plan."), "01:05")
    assert late["ok"] is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "duplicate_recipient_refused" not in kinds
    smap = gateway.superseded_map(job_id)
    assert smap[early["draft_id"]] == "superseded"
    assert late["draft_id"] not in smap
    from app import main as main_mod
    events = list_events(job_id)
    assert len(main_mod._approval_heads(events)) == 1
    page = render_morning_page(f"Job {job_id}", events, job_id=job_id)
    match = re.search(r"Needs you: (\d+) approval", page)
    assert match is not None
    assert int(match.group(1)) == 1
    assert page.count("Approve this exact text") == 1


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
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    runner.execute_tool_call(job_id, _call(
        "record_decision",
        {"outcome": "wake", "reason": "r", "evidence": []}, "c0"),
        "00:46")
    runner.execute_tool_call(job_id, _call("ask_owner", {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff nears", "what_checked": "all",
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


def test_refused_then_folded_with_fake_respond(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()
    seen: dict = {}
    state = {"n": 0}

    def fake_respond(instructions, input_items, **kwargs):
        n = state["n"]
        state["n"] += 1
        if n == 0:
            return {"output": [_call(
                "propose_message",
                _args(R, "purpose_a", "Hello A, first part."), "c1")],
                "text": ""}
        if n == 1:
            seen["refused_input"] = input_items
            return {"output": [_call(
                "propose_message",
                _args(R, "purpose_b", "Hello A, second part."), "c2")],
                "text": ""}
        if n == 2:
            seen["folded_input"] = input_items
            return {"output": [_call(
                "propose_message",
                _args(R, "purpose_a",
                      "Hello A, first part plus second part."), "c3")],
                "text": ""}
        return {"output": [_message("done")], "text": "done"}

    summary = runner.resume_job(job_id, respond_fn=fake_respond)
    assert summary["status"] == "done"
    refused = [e for e in list_events(job_id)
               if e["kind"] == "duplicate_recipient_refused"]
    assert len(refused) == 1
    assert refused[0]["payload"]["recipient"] == R
    assert refused[0]["payload"]["existing_purpose"] == "purpose_a"
    assert refused[0]["payload"]["purpose"] == "purpose_b"
    drafts = [e for e in list_events(job_id) if e["kind"] == "draft"]
    assert len(drafts) == 2
    assert all(d["payload"]["purpose"] == "purpose_a" for d in drafts)
    assert "second part" not in drafts[0]["payload"]["body"]
    assert "first part plus second part" in drafts[1]["payload"]["body"]
    folded = json.dumps(seen["folded_input"])
    assert "already exists in this turn" in folded
    assert "purpose_a" in folded
    assert "fold" in folded
    smap = gateway.superseded_map(job_id)
    assert smap[drafts[0]["id"]] == "superseded"
    assert drafts[1]["id"] not in smap
    from app import main as main_mod
    assert len(main_mod._approval_heads(list_events(job_id))) == 1
