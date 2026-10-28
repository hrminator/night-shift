"""Part 2: State A (the night) on the front door + `?state=` deep links.

The replay renders from the recorded job's own events in the v2 night
layout: collapsed reads, the 22:30 verdict with the model's reason, the
00:38 paper sheet with the quoted line underlined (never a box), the CODE
diff, the six checks as plain-language questions, the decision record,
the CODE deadline line, and the skip link. Deep links select one state.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_mod
from app import states as states_mod

RECORDED = "6c7c7c742513"


def _export() -> dict:
    path = Path("data/runs") / f"job-{RECORDED}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", RECORDED)
    return TestClient(main_mod.app, raise_server_exceptions=False)


def test_check_titles_come_from_runner_definitions():
    from app import runner as runner_mod
    for name in runner_mod.CHECK_NAMES:
        title = states_mod.check_title(name)
        assert title.endswith("?")
        assert title[:1].isupper()
        assert not any(ch.isdigit() for ch in title)
    assert states_mod.check_title("can_ask_now") == states_mod.check_title(
        "can_ask_supplier_or_venue_now")


def test_state_night_renders_the_beat(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/?state=night").text
    assert "SCRIPTED TEST EVENT" in body
    assert "Read 6 sources" in body
    assert "No need to wake you." in body
    assert "Goods will leave our warehouse by 10 November." in body
    assert 'class="quoted"' in body
    assert "Line Muse Spark quoted" in body
    assert "outline:3px solid #f59e0b" not in body
    assert "delivered to your address by 9 November" in body
    assert "Does any source still commit" in body
    assert "baltic_arrival_committed" in body
    assert "Wake, because" in body
    assert "Latest safe time to wake you 01:30" in body
    assert "Skip to 00:47" in body
    assert "?state=question" in body


def test_state_night_model_words_are_verbatim(tmp_path, monkeypatch):
    export = _export()
    reasons = [e["payload"]["reason"] for e in export["events"]
               if e["kind"] == "decision"]
    revised_id = max(e["id"] for e in export["events"]
                     if e["kind"] == "revised_quote")
    notes = [e["payload"]["note"] for e in export["events"]
             if e["kind"] == "check" and e["id"] > revised_id]
    body = _client(tmp_path, monkeypatch).get("/?state=night").text
    for words in reasons + notes:
        assert words in body


def test_state_question_holds_card(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/?state=question").text
    export = _export()
    asked = next(e for e in export["events"]
                 if e["kind"] == "question")
    payload = asked["payload"]
    assert payload["question"] in body
    for option in payload["options"]:
        assert option in body
    assert 'action="/visitor/answer"' in body


def test_state_morning_shows_recorded_morning(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/?state=morning").text
    assert f"Recorded run {RECORDED}" in body
    assert "H-2041" in body


def test_state_question_orders_note_buttons_then_detail(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/?state=question").text
    assert "Muse Spark asks" in body
    assert "Your answer runs live on your own copy of this night" in body
    assert "Change one fact instead" in body
    assert 'action="/visitor/night-b"' in body
    assert "Run the night with this fact" in body
    assert "Why now" in body and "What I checked" in body
    assert "If yes / If no" in body
    assert "The three suppliers" in body
    assert "answer by 01:50" in body
    export = _export()
    asked = next(e for e in export["events"]
                 if e["kind"] == "question")
    first, second = asked["payload"]["options"]
    assert f"<h2>{asked['payload']['question']}</h2>" in body
    assert body.index("</h2>") < body.index(first) < body.index(second)
    assert body.index(second) < body.index("Why now")
    assert body.index(second) < body.index("The three suppliers")


def test_what_checked_splits_at_semicolons():
    assert states_mod.what_checked_items("a; b; c") == ["a", "b", "c"]
    assert states_mod.what_checked_items("") == []


def _seed_waiting_job():
    from app.store import append_event, create_job, set_job_status
    job = create_job(status="running", current_step="waiting_for_owner",
                     virtual_time="00:47")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff", {"source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    question = append_event(job_id, "00:47", "question", {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff 02:00", "what_checked": "a; b",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Bergen: the venue can receive it", "No / not sure"],
    })
    set_job_status(job_id, status="waiting_for_owner",
                   pending_question_id=question["id"],
                   current_step="waiting_for_owner", virtual_time="00:47")
    return job_id


def test_job_page_open_question_is_state_b(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_waiting_job()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{job_id}").text
    assert "Muse Spark asks" in body
    assert "Can the venue receive Wed 08-12?" in body
    assert "Bergen: the venue can receive it" in body
    assert "No / not sure" in body
    assert f'action="/jobs/{job_id}/answer"' in body
    assert "Your answer is a fact" in body
    assert "waiting_for_owner" in body
    assert "handoff" in body and "revised_quote" in body
    assert "The three suppliers" in body
    assert "LIVE · YOUR COPY" in body
    assert "Change one fact instead" not in body


def test_job_page_other_statuses_render(tmp_path, monkeypatch):
    from app.store import append_event, create_job, set_job_status
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    answered = create_job(status="running", virtual_time="00:47")
    append_event(answered["id"], "21:30", "handoff", {"source": "owner"})
    set_job_status(answered["id"], status="answered")
    page = client.get(f"/jobs/{answered['id']}").text
    assert "Answer recorded" in page
    assert "Resume the night from the saved point" in page
    done = create_job(status="done", current_step="done",
                      virtual_time="07:00")
    append_event(done["id"], "21:30", "handoff", {"source": "owner"})
    page = client.get(f"/jobs/{done['id']}").text
    assert "Night complete" in page
    assert "Morning page" in page


def test_default_page_shows_night_then_question(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/").text
    assert "Read 6 sources" in body
    assert "How it decided" in body
    export = _export()
    asked = next(e for e in export["events"]
                 if e["kind"] == "question")
    assert asked["payload"]["question"] in body
    assert "?state=question" in body
