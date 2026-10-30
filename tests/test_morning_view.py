"""Part 4: State C (the morning) renders from the job's own events.

Paper layout: greeting, HOLD LAPSES chip, strip, thermal receipt under
the strip, approval letters exactly as counted (version hash, editable in
place, approved collapsing to an outbox row), For-you notes, Done,
Couldn't-verify, What-was-saved, collapsed How-it-decided, resume panel
with the job's own tokens, cost line, gateway facts on tap. The no-hold
morning reads just as finished.
"""

from __future__ import annotations

import urllib.parse

from fastapi.testclient import TestClient

import app.main as main_mod
from app import gateway
from app.store import append_event, create_job, list_events

RECORDED = "6c7c7c742513"


def _seed_hold_job(drafts=3):
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    purposes = ["order", "venue_note", "baltic_note"]
    recipients = ["Vestland Tekstil", "booking@sjosalen.example.com",
                  "quotes@rannavere-print.example.com"]
    for pos in range(drafts):
        gateway.check_propose_message(job_id, {
            "to": recipients[pos], "subject": f"Subject {pos}",
            "body": f"Exact body {pos}.", "purpose": purposes[pos]}, "01:05")
    append_event(job_id, "01:05", "effect", {
        "tool": "submit_hold", "operation_id": "op-morning",
        "hold_id": "H-2041", "portal": "vestland_portal",
        "acknowledgement": "Vestland Tekstil · Hold H-2041 · "
                           "Simulated supplier system"})
    return job_id


def test_recorded_morning_is_finished(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", RECORDED)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get("/?state=morning").text
    assert "Good morning. The guaranteed van" in body
    assert "HOLD LAPSES 09:00" in body
    assert "Hold confirmed until 09:00" in body
    assert "No purchase commitment" in body
    assert "Owner review due 07:00" in body
    assert "Needs you: 3 approvals" in body
    assert "v·" in body
    assert "Earlier versions" in body
    assert "Done" in body
    assert "t verify" in body
    assert "What was saved" in body
    assert "What was saved is the chance to decide" in body
    assert "How it decided" in body
    assert "The resume" in body
    assert "waited 18 minutes" in body
    assert "2 PDFs pruned at resume" in body
    assert "290,348 input tokens over 17 calls" in body
    assert "53,253" in body and "132,037" in body
    assert "Recorded night 6c7c7c742513 cost $0.26" in body
    assert "Gateway checks: 8 of 8 pass" in body
    assert "permission" in body and "once-only" in body
    assert "RECORDED · 2026-10-27 · MUSE-SPARK-1.3" in body
    assert 'action="/jobs/' not in body


def test_live_morning_letters_carry_hashes_and_forms(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_hold_job()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{job_id}/morning").text
    assert body.count("Approve this exact text") == 3
    assert body.count('textarea class="edit"') == 3
    assert body.count("data-approve") == 3
    assert body.count("data-save") == 3
    assert "Save edited version" in body
    assert "The van order · approve before 09:00" in body
    assert "The venue note" in body
    assert "HOLD LAPSES 09:00" in body
    heads = [e for e in list_events(job_id) if e["kind"] == "draft"]
    for head in heads:
        short = gateway.head_version_hash(head)[:4]
        assert f"v·{short}" in body


def test_no_hold_morning_reads_finished(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    gateway.check_propose_message(job_id, {
        "to": "Vestland Tekstil", "subject": "No order",
        "body": "Not ordering.", "purpose": "order"}, "01:05")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{job_id}/morning").text
    assert "No hold. The slot went at 02:00." in body
    assert "HOLD LAPSES" not in body
    assert "class=\"receipt" not in body
    assert "Needs you: 1 approval" in body
    assert "Approve this exact text" in body
    assert "Done" in body
    assert "t verify" in body
    assert "What was saved" in body


def test_approved_letter_collapses_to_outbox_row(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_hold_job(drafts=1)
    head = next(e for e in list_events(job_id) if e["kind"] == "draft")
    version_hash = gateway.head_version_hash(head)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        f"/jobs/{job_id}/approve",
        content=urllib.parse.urlencode(
            {"draft_id": head["id"], "version_hash": version_hash,
             "virtual_time": "07:00"}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False)
    assert response.status_code == 303
    body = client.get(f"/jobs/{job_id}/morning").text
    assert "approved" in body
    assert "SIMULATED DELIVERY" in body
    assert "Approve this exact text" not in body


def test_resume_panel_uses_job_model_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    asked = append_event(job_id, "00:47", "question", {
        "question": "Q?", "why_now": "w", "what_checked": "c",
        "if_yes": "y", "if_no": "n", "options": ["A", "B"]})
    append_event(job_id, "00:47", "checkpoint",
                 {"question_event_id": asked["id"], "next_input": []})
    append_event(job_id, "01:05", "owner_answer",
                 {"choice": "A", "source": "owner"})
    append_event(job_id, "01:05", "model_call", {
        "call_type": "resume", "model": "muse-spark-1.3", "seconds": 3.0,
        "input_tokens": 9000, "cached_tokens": 3000,
        "output_tokens": 500})
    append_event(job_id, "01:05", "model_call", {
        "call_type": "resume", "model": "muse-spark-1.3", "seconds": 2.0,
        "input_tokens": 3000, "cached_tokens": 1000,
        "output_tokens": 200})
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{job_id}/morning").text
    assert "waited 18 minutes" in body
    assert "12,000 input tokens over 2 calls" in body
    assert "4,000 served from cache" in body
    assert "Measured: this night cost $" in body
