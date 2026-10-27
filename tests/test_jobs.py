"""Job page tests: event list, pending question card, answer posts."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_mod
from app.store import append_event, create_job, get_job, list_events


def _seed_waiting_job():
    job = create_job(status="running", current_step="decision_turn",
                     virtual_time="21:30")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff", {"source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    append_event(job_id, "00:46", "decision",
                 {"outcome": "wake", "reason": "last verified route",
                  "evidence": [1]})
    question = append_event(job_id, "00:47", "question", {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff 02:00", "what_checked": "all sources",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Bergen: the venue can receive it", "No / not sure"],
    })
    append_event(job_id, "00:47", "checkpoint",
                 {"question_event_id": question["id"], "next_input": []})
    from app.store import set_job_status

    set_job_status(job_id, status="waiting_for_owner",
                   pending_question_id=question["id"],
                   current_step="waiting_for_owner", virtual_time="00:47")
    return job_id


def test_job_page_shows_events_and_question(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_waiting_job()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    body = response.text
    assert "waiting_for_owner" in body
    assert "Can the venue receive Wed 08-12?" in body
    assert "Bergen: the venue can receive it" in body
    assert "handoff" in body and "revised_quote" in body


def test_answer_posts_owner_answer_event(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_waiting_job()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        f"/jobs/{job_id}/answer",
        content="choice=Bergen%3A+the+venue+can+receive+it",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    events = list_events(job_id)
    assert events[-1]["kind"] == "owner_answer"
    assert events[-1]["payload"]["source"] == "owner"
    assert get_job(job_id)["status"] == "answered"
