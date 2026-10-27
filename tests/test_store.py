"""Store tests: append-only events, per-job ordering."""

from __future__ import annotations

import sqlite3

from app import store


def test_events_are_append_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = store.create_job(virtual_time="21:30")
    event = store.append_event(job["id"], "21:30", "handoff", {"a": 1})
    conn = store.connect()
    try:
        with conn:
            try:
                conn.execute(
                    "UPDATE events SET kind='edited' WHERE id=?", (event["id"],)
                )
            except sqlite3.IntegrityError:
                pass
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("UPDATE on events should raise")
        with conn:
            try:
                conn.execute("DELETE FROM events WHERE id=?", (event["id"],))
            except sqlite3.IntegrityError:
                pass
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("DELETE on events should raise")
    finally:
        conn.close()
    assert store.list_events(job["id"])[0]["kind"] == "handoff"


def test_event_ordering_and_job_helpers(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = store.create_job(current_step="decision_turn", virtual_time="21:30")
    assert job["status"] == "running"
    kinds = ["handoff", "revised_quote", "claim", "decision", "question"]
    for kind in kinds:
        store.append_event(job["id"], "00:38", kind, {"k": kind})
    events = store.list_events(job["id"])
    assert [e["kind"] for e in events] == kinds
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5]
    updated = store.set_job_status(
        job["id"],
        status="waiting_for_owner",
        pending_question_id=events[-1]["id"],
        virtual_time="00:47",
    )
    assert updated["status"] == "waiting_for_owner"
    assert updated["pending_question_id"] == events[-1]["id"]
    assert store.get_job(job["id"])["virtual_time"] == "00:47"
