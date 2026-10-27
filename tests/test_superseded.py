"""Superseded drafts (pure code): pre-00:38 drafts refresh on resume.

A draft proposed before the revised-quote event is ``superseded_pending``
until a newer draft with the same purpose exists; the resume follow-up
message lists the pre-event drafts by purpose; the morning page collapses
them under "Earlier versions".
"""

from __future__ import annotations

import json

from app import gateway, runner
from app.main import render_morning_page
from app.store import append_event, create_job, list_events

PURPOSE = "comparison for 07:00 review"


def _draft(job_id, purpose, body, virtual_time):
    return append_event(job_id, virtual_time, "draft", {
        "to": "owner", "subject": "sub", "body": body,
        "purpose": purpose, "status": "awaiting_approval"})


def _seed_night():
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    old = _draft(job_id, PURPOSE, "Baltic verified, cheapest", "22:30")
    other = _draft(job_id, "order", "Baltic order draft", "22:30")
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    return job_id, old, other


def test_pre_event_drafts_pending_until_reissued(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, old, other = _seed_night()
    assert gateway.superseded_map(job_id) == {
        old["id"]: "superseded_pending", other["id"]: "superseded_pending"}
    new = _draft(job_id, PURPOSE, "Baltic arrival unverified", "01:05")
    assert new["id"] not in gateway.superseded_map(job_id)
    assert gateway.superseded_map(job_id) == {
        old["id"]: "superseded", other["id"]: "superseded_pending"}


def test_resume_instructions_list_pre_event_drafts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, old, _ = _seed_night()
    answer = append_event(job_id, "01:05", "owner_answer",
                          {"choice": "Bergen: the venue can receive it",
                           "source": "owner"})
    text = runner.build_resume_instructions(job_id, answer)
    assert PURPOSE in text
    assert "SAME purpose" in text


def _answer_and_checkpoint(job_id):
    question = append_event(job_id, "00:47", "question", {
        "question": "Q?", "why_now": "w", "what_checked": "c",
        "if_yes": "y", "if_no": "n", "options": ["A", "B"]})
    append_event(job_id, "00:47", "checkpoint", {
        "question_event_id": question["id"], "next_input": [{
            "type": "function_call", "call_id": "ask1",
            "name": "ask_owner", "arguments": "{}"}]})
    runner.store_answer(job_id, "Bergen: the venue can receive it")


def _propose_call(purpose, body, call_id):
    return {"type": "function_call", "call_id": call_id,
            "name": "propose_message",
            "arguments": json.dumps({"to": "owner", "subject": "sub",
                                     "body": body, "purpose": purpose})}


def test_resume_reissue_clears_pending_with_fake_respond(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, old, _ = _seed_night()
    _answer_and_checkpoint(job_id)
    seen = {}

    def fake_respond(instructions, input_items, **kwargs):
        seen.setdefault("instructions", instructions)
        if "calls" not in seen:
            seen["calls"] = 1
            return {"output": [_propose_call(
                PURPOSE, "Baltic arrival now unverified", "c1")], "text": ""}
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "done"}]}], "text": "done"}

    assert PURPOSE in runner.build_resume_instructions(
        job_id, [e for e in list_events(job_id)
                 if e["kind"] == "owner_answer"][-1])
    result = runner.resume_job(job_id, respond_fn=fake_respond)
    assert result["status"] == "done"
    assert PURPOSE in seen["instructions"]
    assert gateway.superseded_map(job_id)[old["id"]] == "superseded"
    page = render_morning_page(f"Job {job_id}", list_events(job_id),
                               job_id=job_id)
    assert "Earlier versions" in page
    assert "superseded" in page
    assert "Baltic arrival now unverified" in page


def test_pending_draft_shown_collapsed_before_reissue(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, old, _ = _seed_night()
    page = render_morning_page(f"Job {job_id}", list_events(job_id),
                               job_id=job_id)
    assert "Earlier versions" in page
    assert "superseded_pending" in page
