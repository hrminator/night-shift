"""Part 5: contract tests for the change-one-fact control (fake respond).

The control creates a fresh job with no replayed reasoning; the override
changes exactly one line of exactly one fixture; the cap and the 2-slot
semaphore apply; the recorded Night B serves when the cap is reached.
"""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

import app.main as main_mod
from app import night_b as night_b_mod
from app import replay as replay_mod
from app import runner as runner_mod
from app import spend as spend_mod
from app.store import day_spend_usd, get_job, list_events, list_jobs

CONTACT = ("Kari Strandli, studio coordinator, "
           "orders@fjord-fern.example.com, +47 22 00 11 22")
PRINT_FILE = "fjord-fern-logo-print.pdf"
VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
VENUE_SOURCE = "Venue booking confirmation (Sjøsalen)"


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _text(words):
    return {"type": "message", "content": [
        {"type": "output_text", "text": words}]}


def _venue_claim_id():
    for job in list_jobs():
        for event in list_events(job["id"]):
            payload = event.get("payload") or {}
            if event["kind"] == "claim" \
                    and "venue" in str(payload.get("source", "")).lower():
                return event["id"]
    return None


def _hold_payload(recipient_claim_id):
    return {
        "portal": "vestland_portal",
        "action": "capacity_hold",
        "product": "100 tote bags with logo",
        "quantity": 100,
        "print_file": PRINT_FILE,
        "address": VENUE_ADDRESS,
        "delivery_window": "Wed Nov 11 08:00-12:00",
        "ordering_contact": CONTACT,
        "recipient_can_receive": True,
        "cost": 0, "binding": False, "hold_ends": "09:00",
        "sources": {
            "recipient_can_receive": {"kind": "claim",
                                      "id": recipient_claim_id},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"}}}


def _scripted_night_b(seen):
    """A correct quiet Night B: hold in reassess, never a question."""
    counts: dict[str, int] = {}

    def fake(instructions, input_items, **kwargs):
        seen.append(list(input_items))
        call_type = kwargs.get("call_type", "?")
        counts[call_type] = counts.get(call_type, 0) + 1
        step = counts[call_type]
        usage = {"input_tokens": 1000, "output_tokens": 100,
                 "input_tokens_details": {"cached_tokens": 0}}
        if call_type == "read":
            if step == 1:
                return {"output": [_call(
                    "record_claim",
                    {"source": VENUE_SOURCE,
                     "quote": night_b_mod.night_b_sentence(),
                     "claim": "venue receives Wed 08-16"}, "c1")],
                    "text": "", "usage": usage}
            if step == 2:
                return {"output": [_call(
                    "record_decision",
                    {"outcome": "no_wake",
                     "reason": "Baltic Q-1187 commits arrival",
                     "evidence": [_venue_claim_id()]}, "d1")],
                    "text": "", "usage": usage}
            return {"output": [_text("read done")], "text": "read done",
                    "usage": usage}
        if step == 1:
            return {"output": [_call(
                "record_decision",
                {"outcome": "act_under_permission",
                 "reason": "last verified route, venue confirms receipt",
                 "evidence": [_venue_claim_id()]}, "d2")],
                "text": "", "usage": usage}
        if step == 2:
            return {"output": [_call(
                "submit_hold", _hold_payload(_venue_claim_id()), "h1")],
                "text": "", "usage": usage}
        return {"output": [_text("night done")], "text": "night done",
                "usage": usage}

    return fake


def _stub_uploads(monkeypatch):
    monkeypatch.setattr(runner_mod, "upload_pdf",
                        lambda path: {"id": "file-stub"})
    monkeypatch.setattr(runner_mod, "delete_file", lambda file_id: None)


def _wait_for_terminal(job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job is not None \
                and job["status"] in night_b_mod.TERMINAL_STATUSES:
            return job
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} never reached a terminal status")


def _wait_for_slots(timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        first = spend_mod.acquire_visitor_slot("probe-1")
        second = spend_mod.acquire_visitor_slot("probe-2")
        if first is not None and second is not None:
            spend_mod.release_visitor_slot(first, "probe-1")
            spend_mod.release_visitor_slot(second, "probe-2")
            return True
        if first is not None:
            spend_mod.release_visitor_slot(first, "probe-1")
        if second is not None:
            spend_mod.release_visitor_slot(second, "probe-2")
        time.sleep(0.2)
    raise AssertionError("visitor slots were never released")


def _has_reasoning(items) -> bool:
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "reasoning" \
                or "encrypted_content" in item:
            return True
        if str(item.get("type", "")).startswith("reasoning"):
            return True
    return False


def test_control_creates_fresh_job_without_replayed_reasoning(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seen: list = []
    monkeypatch.setattr(main_mod, "LIVE_RESPOND_FN",
                        _scripted_night_b(seen))
    _stub_uploads(monkeypatch)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post("/visitor/night-b", follow_redirects=False)
    assert response.status_code == 303
    job_id = response.headers["location"].rsplit("/", 1)[-1]
    job = _wait_for_terminal(job_id)
    assert job["status"] == "done"
    events = list_events(job_id)
    handoffs = [e for e in events if e["kind"] == "handoff"]
    assert len(handoffs) == 1
    assert handoffs[0]["virtual_time"] == "21:30"
    assert handoffs[0]["payload"]["variant"] == "contrast"
    assert not any((e.get("payload") or {}).get("copied_from_recorded")
                   for e in events)
    assert not any(e["kind"] == "question" for e in events)
    effects = [e for e in events if e["kind"] == "effect"]
    assert len(effects) == 1
    assert effects[0]["payload"]["hold_id"] == "H-2041"
    assert effects[0]["virtual_time"] == "00:39"
    revised = [e for e in events if e["kind"] == "revised_quote"]
    assert len(revised) == 1
    assert effects[0]["id"] > revised[0]["id"]
    assert seen, "the fake model was never called"
    assert not any(_has_reasoning(items) for items in seen)
    progress = client.get(f"/visitor/night/{job_id}")
    assert progress.status_code == 200
    assert "Night complete" in progress.text
    assert "(+0s)" in progress.text
    morning = client.get(f"/jobs/{job_id}/morning")
    assert morning.status_code == 200
    assert "H-2041" in morning.text
    raw = client.get(f"/jobs/{job_id}/events")
    assert raw.status_code == 200
    assert raw.json()["job_id"] == job_id
    assert day_spend_usd(spend_mod.today_utc()) > 0
    _wait_for_slots()


def test_override_changes_one_line_of_one_fixture():
    diff = night_b_mod.fixture_diff()
    assert list(diff) == ["venue_confirmation.md"]
    change = diff["venue_confirmation.md"]
    assert change["removed"] == []
    assert change["added"] == [night_b_mod.night_b_sentence()]
    assert night_b_mod.night_b_sentence() == (
        "Deliveries for your event can be received Wed Nov 11,"
        " 08:00-16:00 at the goods entrance.")
    assert "Thursday event only" in night_b_mod.night_a_sentence()


def _write_contrast_record(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    record = {"job_id": "recb00000007", "exported": True, "events": [
        {"id": 1, "job_id": "recb00000007", "seq": 1,
         "virtual_time": "21:30", "kind": "handoff",
         "payload": {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": "contrast"},
         "created_at": "2026-10-28T12:00:00+00:00"},
        {"id": 2, "job_id": "recb00000007", "seq": 2,
         "virtual_time": "00:38", "kind": "effect",
         "payload": {"tool": "submit_hold", "operation_id": "b-op",
                     "hold_id": "H-2041",
                     "acknowledgement": "Vestland Tekstil · Hold H-2041"},
         "created_at": "2026-10-28T12:01:00+00:00"},
    ]}
    (runs / "job-recb00000007.json").write_text(
        json.dumps(record), encoding="utf-8")


def test_cap_serves_recorded_night_b(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_contrast_record(tmp_path)
    monkeypatch.setattr(replay_mod, "runs_dirs",
                        lambda: [tmp_path / "runs"])
    monkeypatch.delenv("RECORDED_JOB_B", raising=False)
    monkeypatch.setenv("DAILY_CAP_USD", "0")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post("/visitor/night-b", follow_redirects=False)
    assert response.status_code == 200
    assert "daily spend cap" in response.text
    assert "Recorded Night B recb00000007" in response.text
    assert "H-2041" in response.text
    assert list_jobs() == []


def test_busy_slots_serve_recorded_night_b(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_contrast_record(tmp_path)
    monkeypatch.setattr(replay_mod, "runs_dirs",
                        lambda: [tmp_path / "runs"])
    monkeypatch.delenv("RECORDED_JOB_B", raising=False)
    assert spend_mod.acquire_visitor_slot("tester-1") is not None
    assert spend_mod.acquire_visitor_slot("tester-2") is not None
    try:
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        response = client.post("/visitor/night-b", follow_redirects=False)
        assert response.status_code == 200
        assert "2 live resumes already running" in response.text
        assert "Recorded Night B recb00000007" in response.text
        assert list_jobs() == []
    finally:
        spend_mod.release_visitor_slot("visitor-resume-0", "tester-1")
        spend_mod.release_visitor_slot("visitor-resume-1", "tester-2")


def test_pinned_recording_wins_over_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_contrast_record(tmp_path)
    monkeypatch.setenv("RECORDED_JOB_B", "recb00000007")
    monkeypatch.setenv("DAILY_CAP_USD", "0")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post("/visitor/night-b", follow_redirects=False)
    assert response.status_code == 200
    assert "Recorded Night B recb00000007" in response.text


def test_night_b_job_page_hashes_against_hero_copy(tmp_path, monkeypatch):
    """Part 4 verbatim: different fixture hash, same policy hash."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seen: list = []
    _stub_uploads(monkeypatch)
    summary = night_b_mod.run_fresh_night_b(
        respond_fn=_scripted_night_b(seen))
    assert summary["status"] == "done"
    night_b_id = summary["job_id"]
    record = {"job_id": "rec-hero-1", "exported": True, "events": [
        {"id": 1, "job_id": "rec-hero-1", "seq": 1,
         "virtual_time": "21:30", "kind": "handoff",
         "payload": {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": "hero"},
         "created_at": "2026-10-27T12:00:00+00:00"},
        {"id": 2, "job_id": "rec-hero-1", "seq": 2,
         "virtual_time": "00:47", "kind": "question",
         "payload": {"question": "Can it receive?",
                     "options": ["Yes", "No"]},
         "created_at": "2026-10-27T12:04:00+00:00"},
        {"id": 3, "job_id": "rec-hero-1", "seq": 3,
         "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 2, "next_input": []},
         "created_at": "2026-10-27T12:04:30+00:00"},
    ]}
    hero_id = replay_mod.copy_job_for_visitor(record, "Yes")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    b_page = client.get(f"/jobs/{night_b_id}").text
    hero_page = client.get(f"/jobs/{hero_id}").text
    policy = night_b_mod.policy_hash()
    assert policy in b_page and policy in hero_page
    hero_fixtures = night_b_mod.fixture_set_hash("hero")
    b_fixtures = night_b_mod.fixture_set_hash("contrast")
    assert hero_fixtures in hero_page
    assert b_fixtures in b_page
    assert b_fixtures not in hero_page
