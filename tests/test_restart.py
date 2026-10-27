"""Contract test 6 (pure code, no model): a restart mid-night resumes the
right job at the right step.

Two crash points: after the 00:38 event is appended but before the reassess
turn, and after the checkpoint. On startup `resume_open_jobs()` finds the
open job and continues from the last durable event (reassess, or
waiting_for_owner), holding a run lock per job so two processes never run
the same job.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.main as main_mod
from app import runner
from app.store import (acquire_lock, append_event, create_job, get_job,
                       list_events, release_lock)

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"


def _call(name, args, call_id):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def _text(words):
    return {
        "type": "message",
        "content": [{"type": "output_text", "text": words}],
    }


def _seed_crashed_after_event():
    """Process stopped after the 00:38 event, before the reassess turn."""
    job = create_job(status="running", current_step="read_turn",
                     virtual_time="00:38")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner",
                  "variant": "hero"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    return job_id


def _seed_waiting():
    """Process stopped after the checkpoint; the question is pending."""
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner",
                  "variant": "hero"})
    question = append_event(job_id, "00:47", "question", {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff 02:00", "what_checked": "all sources",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Bergen: the venue can receive it", "No / not sure"]})
    from app.store import set_job_status
    ask = _call("ask_owner", {"question": "Can the venue receive Wed 08-12?"}, "ask-1")
    runner.save_checkpoint(job_id, [{"type": "message", "role": "user", "content": "hi"}, ask], question["id"])
    assert get_job(job_id)["status"] == "waiting_for_owner"
    return job_id


def _seed_answered():
    """Checkpoint plus an owner answer; the resume never ran."""
    job_id = _seed_waiting()
    runner.store_answer(job_id, "Bergen: the venue can receive it",
                        virtual_time="01:05")
    return job_id


def _hold_args(answer_id: int) -> dict:
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
            return {"output": [_call("submit_hold", _hold_args(aid), "s1")],
                    "text": ""}
        if 1 <= n <= 3:
            return {"output": [_call(
                "propose_message",
                {"to": f"Recipient {n}", "subject": f"Subject {n}",
                 "body": f"Exact body {n}", "purpose": f"purpose {n}"},
                f"p{n}")], "text": ""}
        return {"output": [_text("night complete")], "text": "night complete"}

    return stub


def _boom(_instructions, _input_items, **_kwargs):
    raise AssertionError("no model call expected on this path")


def test_restart_after_0038_reruns_reassess(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_crashed_after_event()
    seen = []

    def fake_reassess(crashed_id, respond_fn):
        seen.append((crashed_id, respond_fn))
        return {"status": "waiting_for_owner", "job_id": crashed_id}

    results = runner.resume_open_jobs(respond_fn=_boom,
                                      reassess_fn=fake_reassess)
    assert results[job_id]["status"] == "waiting_for_owner"
    assert [call[0] for call in seen] == [job_id]
    assert acquire_lock(f"job:{job_id}:run", "another-process") is True
    release_lock(f"job:{job_id}:run", "another-process")


def test_restart_after_checkpoint_stays_waiting(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_waiting()

    def fake_reassess(crashed_id, respond_fn):
        raise AssertionError("reassess must not run after a checkpoint")

    results = runner.resume_open_jobs(respond_fn=_boom,
                                      reassess_fn=fake_reassess)
    assert results[job_id]["status"] == "waiting_for_owner"
    assert get_job(job_id)["status"] == "waiting_for_owner"


def test_restart_with_answer_resumes_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_answered()

    def fake_reassess(crashed_id, respond_fn):
        raise AssertionError("an answered job resumes, not reassesses")

    results = runner.resume_open_jobs(
        respond_fn=_resume_stub(job_id), reassess_fn=fake_reassess)
    assert results[job_id]["status"] == "resumed"
    assert get_job(job_id)["status"] == "done"
    assert "effect" in [e["kind"] for e in list_events(job_id)]


def test_run_lock_blocks_second_process(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_crashed_after_event()
    assert acquire_lock(f"job:{job_id}:run", "process-A") is True

    def fake_reassess(crashed_id, respond_fn):
        raise AssertionError("a locked job must not run twice")

    results = runner.resume_open_jobs(respond_fn=_boom,
                                      reassess_fn=fake_reassess)
    assert results[job_id]["status"] == "locked"
    assert release_lock(f"job:{job_id}:run", "process-A") is True
    seen = []
    runner.resume_open_jobs(
        respond_fn=_boom,
        reassess_fn=lambda crashed_id, rf: seen.append(crashed_id) or {
            "status": "noop", "job_id": crashed_id})
    assert seen == [job_id]


def test_lock_expiry_and_ownership(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert acquire_lock("night", "A") is True
    assert acquire_lock("night", "B") is False
    assert release_lock("night", "B") is False
    assert release_lock("night", "A") is True
    assert acquire_lock("night", "B") is True
    assert acquire_lock("expired", "A", ttl_seconds=-1) is True
    assert acquire_lock("expired", "B") is True


def test_startup_wiring_behind_flag(tmp_path, monkeypatch):
    import app.runner as runner_mod
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seen = []
    monkeypatch.setattr(runner_mod, "resume_open_jobs",
                        lambda: seen.append(True) or {})
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    assert client.get("/").status_code == 200
    assert seen == []
    monkeypatch.setenv("NIGHT_SHIFT_AUTO_RESUME", "1")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    with client:
        pass
    assert seen == [True]
