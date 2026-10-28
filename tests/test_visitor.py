"""Contract test 11 + front-door guards (pure code, no model).

11: two visitors answering the same recorded question produce two separate
jobs, each with exactly one hold, and the recorded export is unchanged.
Plus: the replay page renders from the export; the spend cap and the
2-resume semaphore fall back to the recorded morning page; POST /jobs/run
needs the X-Run-Token header.
"""

from __future__ import annotations

import json
import urllib.parse

from fastapi.testclient import TestClient

import app.main as main_mod
from app import runner
from app import replay as replay_mod
from app import spend as spend_mod
from app.store import list_events, list_jobs

CONTACT = ("Kari Strandli, studio coordinator, "
           "orders@fjord-fern.example.com, +47 22 00 11 22")
PRINT_FILE = "fjord-fern-logo-print.pdf"
VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
OPTIONS = ["Yes - Sjosalen can receive Wed 08-12", "No - cannot receive then"]
QUESTION = "Can Sjosalen receive the van Wed Nov 11 08:00-12:00?"


def _record():
    check_names = ["baltic_arrival_committed", "original_quote_still_valid",
                   "nordtrykk_can_make_nov10", "vestland_can_deliver_oslo",
                   "files_say_venue_accepts_delivery", "can_ask_supplier_or_venue_now"]
    events = [
        {"id": 1, "job_id": "rec00000001", "seq": 1, "virtual_time": "21:30",
         "kind": "handoff",
         "payload": {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": "hero"},
         "created_at": "2026-10-27T12:00:00+00:00"},
        {"id": 2, "job_id": "rec00000001", "seq": 2, "virtual_time": "22:30",
         "kind": "claim",
         "payload": {"source": "Vestland portal record",
                     "quote": "Wed Nov 11 08:00-12:00",
                     "claim": "van guaranteed"},
         "created_at": "2026-10-27T12:01:00+00:00"},
    ]
    for pos, name in enumerate(check_names):
        events.append(
            {"id": 3 + pos, "job_id": "rec00000001", "seq": 3 + pos,
             "virtual_time": "00:39", "kind": "check",
             "payload": {"name": name,
                         "result": "pass" if pos == 4 else "fail",
                         "evidence": [2], "note": f"note for {name}"},
             "created_at": "2026-10-27T12:02:00+00:00"})
    events += [
        {"id": 9, "job_id": "rec00000001", "seq": 9, "virtual_time": "00:39",
         "kind": "decision",
         "payload": {"outcome": "wake", "reason": "owner holds the last fact",
                     "evidence": [2]},
         "created_at": "2026-10-27T12:03:00+00:00"},
        {"id": 10, "job_id": "rec00000001", "seq": 10,
         "virtual_time": "00:39", "kind": "revised_quote",
         "payload": {"quote": "Q-1187-B", "replaces": "Q-1187"},
         "created_at": "2026-10-27T12:03:30+00:00"},
        {"id": 11, "job_id": "rec00000001", "seq": 11,
         "virtual_time": "00:47", "kind": "question",
         "payload": {"question": QUESTION, "why_now": "cutoff 02:00",
                     "what_checked": "all six checks", "if_yes": "one hold",
                     "if_no": "no hold", "options": OPTIONS},
         "created_at": "2026-10-27T12:04:00+00:00"},
        {"id": 12, "job_id": "rec00000001", "seq": 12,
         "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 11,
                     "next_input": [
                         {"type": "message", "role": "user",
                          "content": [{"type": "input_text",
                                       "text": "night so far"}]},
                         {"type": "function_call", "call_id": "ask-1",
                          "name": "ask_owner", "arguments": "{}"}]},
         "created_at": "2026-10-27T12:04:30+00:00"},
        # Past the checkpoint: none of this may leak into a visitor copy.
        {"id": 13, "job_id": "rec00000001", "seq": 13,
         "virtual_time": "01:05", "kind": "owner_answer",
         "payload": {"choice": OPTIONS[0], "source": "owner"},
         "created_at": "2026-10-27T12:05:00+00:00"},
        {"id": 14, "job_id": "rec00000001", "seq": 14,
         "virtual_time": "01:05", "kind": "effect",
         "payload": {"tool": "submit_hold", "operation_id": "rec-op",
                     "hold_id": "H-2041",
                     "acknowledgement": "Vestland Tekstil · Hold H-2041"},
         "created_at": "2026-10-27T12:06:00+00:00"},
        {"id": 15, "job_id": "rec00000001", "seq": 15,
         "virtual_time": "01:05", "kind": "draft",
         "payload": {"to": "Vestland", "subject": "Order",
                     "body": "Recorded body.", "purpose": "order",
                     "status": "awaiting_approval"},
         "created_at": "2026-10-27T12:06:30+00:00"},
    ]
    return {"job_id": "rec00000001", "exported": True, "events": events}


def _write_record(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / "job-rec00000001.json"
    path.write_text(json.dumps(_record(), ensure_ascii=False),
                    encoding="utf-8")
    return path


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _resume_stub(job_id: str):
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        answers = [e for e in list_events(job_id)
                   if e["kind"] == "owner_answer"]
        aid = answers[-1]["id"]
        n = state["n"]
        state["n"] += 1
        if n == 0:
            return {"output": [_call("submit_hold", {
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
                    "recipient_can_receive": {"kind": "owner_answer",
                                              "id": aid},
                    "route": {"kind": "portal", "version": 1},
                    "window": {"kind": "portal", "version": 1},
                    "ordering_contact": {"kind": "studio_file"},
                    "print_file": {"kind": "studio_file"}}},
                "s1")], "text": ""}
        if 1 <= n <= 3:
            return {"output": [_call(
                "propose_message",
                {"to": f"Recipient {n}", "subject": f"Subject {n}",
                 "body": f"Exact body {n}", "purpose": f"purpose {n}"},
                f"p{n}")], "text": ""}
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "night complete"}]}], "text": "x"}

    return stub


def test_two_visitors_two_jobs_one_hold_each(tmp_path, monkeypatch):
    """Contract 11: separate jobs, one hold each, export untouched."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    recorded = _write_record(tmp_path)
    before = recorded.read_bytes()
    record = json.loads(before.decode("utf-8"))

    # Both visitors answer yes: a "no" answer is refused by the gateway
    # (sources check), so a no-answer copy would hold nothing.
    first = replay_mod.copy_job_for_visitor(record, OPTIONS[0])
    second = replay_mod.copy_job_for_visitor(record, OPTIONS[0])
    assert first != second
    assert recorded.read_bytes() == before

    for job_id, choice in ((first, OPTIONS[0]), (second, OPTIONS[0])):
        kinds = [e["kind"] for e in list_events(job_id)]
        assert "checkpoint" in kinds
        assert "owner_answer" in kinds
        assert "effect" not in kinds
        assert "draft" not in kinds
        answers = [e for e in list_events(job_id)
                   if e["kind"] == "owner_answer"]
        assert answers[-1]["payload"]["choice"] == choice
        checkpoints = [e for e in list_events(job_id)
                       if e["kind"] == "checkpoint"]
        questions = [e for e in list_events(job_id)
                     if e["kind"] == "question"]
        assert checkpoints[-1]["payload"]["question_event_id"] == \
            questions[-1]["id"]

    summary = runner.resume_job(first, respond_fn=_resume_stub(first))
    assert summary["status"] == "done"
    summary = runner.resume_job(second, respond_fn=_resume_stub(second))
    assert summary["status"] == "done"
    ops = []
    for job_id in (first, second):
        effects = [e for e in list_events(job_id)
                   if e["kind"] == "effect"]
        assert len(effects) == 1
        assert effects[0]["payload"].get("hold_id") == "H-2041"
        ops.append(effects[0]["payload"]["operation_id"])
    assert ops[0] != ops[1]
    assert recorded.read_bytes() == before


def _form(**fields):
    return urllib.parse.urlencode(fields)


def test_front_door_replays_recorded_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_record(tmp_path)
    monkeypatch.setenv("RECORDED_JOB", "rec00000001")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Real muse-spark-1.3 calls recorded on 2026-10-27" in body
    assert "Supplier system and mail simulated" in body
    assert "Wed Nov 11 08:00-12:00" in body
    assert "Q-1187-B" in body
    assert "files_say_venue_accepts_delivery" in body
    assert "owner holds the last fact" in body
    assert QUESTION in body
    assert OPTIONS[0] in body and OPTIONS[1] in body
    assert "How it decided" in body
    assert "Results in the README" in body


def test_spend_cap_serves_recorded_morning(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_record(tmp_path)
    monkeypatch.setenv("RECORDED_JOB", "rec00000001")
    monkeypatch.setenv("DAILY_CAP_USD", "0")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        "/visitor/answer", content=_form(choice=OPTIONS[0]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False)
    assert response.status_code == 200
    assert "daily spend cap" in response.text
    assert "Recorded run rec00000001" in response.text
    assert list_jobs() == []


def test_two_busy_slots_serve_recorded_morning(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write_record(tmp_path)
    monkeypatch.setenv("RECORDED_JOB", "rec00000001")
    assert spend_mod.acquire_visitor_slot("tester-1") is not None
    assert spend_mod.acquire_visitor_slot("tester-2") is not None
    assert spend_mod.acquire_visitor_slot("tester-3") is None
    try:
        client = TestClient(main_mod.app, raise_server_exceptions=False)
        response = client.post(
            "/visitor/answer", content=_form(choice=OPTIONS[1]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False)
        assert response.status_code == 200
        assert "2 live resumes already running" in response.text
        assert list_jobs() == []
    finally:
        spend_mod.release_visitor_slot("visitor-resume-0", "tester-1")
        spend_mod.release_visitor_slot("visitor-resume-1", "tester-2")


def test_run_token_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    assert client.post("/jobs/run").status_code == 403
    assert client.post("/jobs/run",
                       headers={"X-Run-Token": "wrong"}).status_code == 403
    monkeypatch.setenv("RUN_TOKEN", "test-token")
    monkeypatch.setattr("app.runner.run_job",
                        lambda variant="hero", owner_job=False: {
                            "job_id": "abc",
                                               "status": "done"})
    response = client.post("/jobs/run", headers={"X-Run-Token": "test-token"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/jobs/abc"


def test_spend_math_uses_spark_prices():
    assert spend_mod.cost_usd(1_000_000, 0, 0) == 1.25
    assert spend_mod.cost_usd(1_000_000, 1_000_000, 0) == 0.15
    assert spend_mod.cost_usd(0, 0, 1_000_000) == 4.25


def test_old_check_name_renders_with_new_name():
    """Stored can_ask_now events render as can_ask_supplier_or_venue_now."""
    event = {"id": 1, "job_id": "rec-old", "seq": 1,
             "virtual_time": "00:41", "kind": "check",
             "payload": {"name": "can_ask_now", "result": "fail",
                         "evidence": [], "note": "no reply in time"},
             "created_at": "2026-10-27T12:02:00+00:00"}
    assert main_mod.display_check_name("can_ask_now") == \
        "can_ask_supplier_or_venue_now"
    assert main_mod.display_check_name(
        "can_ask_supplier_or_venue_now") == "can_ask_supplier_or_venue_now"
    for html in (main_mod._replay_timeline([event]),
                 main_mod._decision_section([event]),
                 main_mod.render_morning_page("Job rec-old", [event])):
        assert "can_ask_supplier_or_venue_now" in html
        assert "can_ask_now" not in html
    assert "can_ask_supplier_or_venue_now" in main_mod._summarize(
        "check", event["payload"])
