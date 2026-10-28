"""Part 5: the live steps behind POST /visitor/answer (fake respond).

A tap copies the recorded run and resumes it in a background thread under
the spend cap and semaphore; GET /visitor/answer/{id} shows the real
steps as they are logged, each with elapsed seconds, no spinner, the chip
on LIVE. Cap and slot refusals serve the recorded morning with the chip
back on RECORDED.
"""

from __future__ import annotations

import json
import time
import urllib.parse

from fastapi.testclient import TestClient

import app.main as main_mod
from app import spend as spend_mod
from app.store import get_job, list_events, list_jobs

CONTACT = ("Kari Strandli, studio coordinator, "
           "orders@fjord-fern.example.com, +47 22 00 11 22")
PRINT_FILE = "fjord-fern-logo-print.pdf"
VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
OPTIONS = ["Yes - Sjosalen can receive Wed 08-12", "No - cannot receive then"]
QUESTION = "Can Sjosalen receive the van Wed Nov 11 08:00-12:00?"


def _record():
    return {"job_id": "rec00000001", "exported": True, "events": [
        {"id": 1, "job_id": "rec00000001", "seq": 1,
         "virtual_time": "21:30", "kind": "handoff",
         "payload": {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": "hero"},
         "created_at": "2026-10-27T12:00:00+00:00"},
        {"id": 2, "job_id": "rec00000001", "seq": 2,
         "virtual_time": "00:47", "kind": "question",
         "payload": {"question": QUESTION, "why_now": "cutoff 02:00",
                     "what_checked": "all six checks", "if_yes": "one hold",
                     "if_no": "no hold", "options": OPTIONS},
         "created_at": "2026-10-27T12:04:00+00:00"},
        {"id": 3, "job_id": "rec00000001", "seq": 3,
         "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 2,
                     "next_input": [
                         {"type": "function_call", "call_id": "ask-1",
                          "name": "ask_owner", "arguments": "{}"}]},
         "created_at": "2026-10-27T12:04:30+00:00"},
    ]}


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _any_job_resume_stub():
    """A hold plus three drafts for whatever copy is resuming."""
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        jobs = list_jobs()
        assert jobs, "the copy must exist before the first model call"
        job_id = jobs[-1]["id"]
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


def _wait_for_text(client, url, marker, timeout=30.0):
    deadline = time.time() + timeout
    body = ""
    while time.time() < deadline:
        body = client.get(url).text
        if marker in body:
            return body
        time.sleep(0.3)
    raise AssertionError(f"{url} never showed {marker!r}")


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


def test_answer_runs_live_with_logged_steps(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    recorded = runs / "job-rec00000001.json"
    recorded.write_text(json.dumps(_record()), encoding="utf-8")
    before = recorded.read_bytes()
    monkeypatch.setenv("RECORDED_JOB", "rec00000001")
    monkeypatch.setattr(main_mod, "LIVE_RESPOND_FN",
                        _any_job_resume_stub())
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        "/visitor/answer",
        content=urllib.parse.urlencode({"choice": OPTIONS[0]}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/visitor/answer/")
    job_id = location.rsplit("/", 1)[-1]
    assert get_job(job_id) is not None
    early = client.get(location).text
    assert "LIVE · YOUR COPY" in early
    assert "Answer recorded" in early
    assert "(+0s)" in early
    assert "spinner" not in early.lower()
    body = _wait_for_text(client, location, "Night complete")
    assert "Morning page" in body and "Raw event log" in body
    morning = client.get(f"/jobs/{job_id}/morning").text
    assert "H-2041" in morning
    assert "LIVE · YOUR COPY" in morning
    assert recorded.read_bytes() == before
    _wait_for_slots()


def test_refusals_show_recorded_morning_on_recorded_chip(tmp_path,
                                                         monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "job-rec00000001.json").write_text(
        json.dumps(_record()), encoding="utf-8")
    monkeypatch.setenv("RECORDED_JOB", "rec00000001")
    monkeypatch.setenv("DAILY_CAP_USD", "0")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        "/visitor/answer",
        content=urllib.parse.urlencode({"choice": OPTIONS[0]}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False)
    assert response.status_code == 200
    assert "daily spend cap" in response.text
    assert "RECORDED ·" in response.text
    assert "LIVE · YOUR COPY" not in response.text
    assert list_jobs() == []
