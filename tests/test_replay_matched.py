"""Matched replay mechanics (pure code, stub model, no network).

The replay arm replays the checkpoint input with its reasoning items and
no files; the resend arm drops the reasoning and re-attaches the source
documents. Live token means come from scripts/replay_matched.py runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import replay_matched as matched
from app import runner
from app.store import list_events

OPTIONS = ["Yes - Sjosalen can receive Wed 08-12", "No - cannot receive then"]
QUESTION = "Can Sjosalen receive the van Wed Nov 11 08:00-12:00?"


def _record():
    return {"job_id": "rec-matched-1", "exported": True, "events": [
        {"id": 1, "job_id": "rec-matched-1", "seq": 1,
         "virtual_time": "21:30", "kind": "handoff",
         "payload": {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": "hero"},
         "created_at": "2026-10-27T12:00:00+00:00"},
        {"id": 2, "job_id": "rec-matched-1", "seq": 2,
         "virtual_time": "00:47", "kind": "question",
         "payload": {"question": QUESTION, "why_now": "cutoff",
                     "what_checked": "all", "if_yes": "hold",
                     "if_no": "no hold", "options": OPTIONS},
         "created_at": "2026-10-27T12:04:00+00:00"},
        {"id": 3, "job_id": "rec-matched-1", "seq": 3,
         "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 2, "next_input": [
             {"type": "message", "role": "user", "content": [
                 {"type": "input_file", "file_id": "file-dead"},
                 {"type": "input_text", "text": "night so far"}]},
             {"type": "reasoning", "id": "rs-stub",
              "encrypted_content": "stub-encrypted"},
             {"type": "function_call", "call_id": "ask-1",
              "name": "ask_owner", "arguments": "{}"}]},
         "created_at": "2026-10-27T12:04:30+00:00"},
    ]}


def _capture_stub(seen):
    def stub(instructions, input_items, **kwargs):
        seen.append(list(input_items))
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "stub done"}]}], "text": "stub"}
    return stub


def _input_file_parts(first_input):
    parts = []
    for entry in first_input:
        content = entry.get("content")
        if entry.get("type") == "message" and isinstance(content, list):
            parts.extend(part for part in content
                         if part.get("type") == "input_file")
    return parts


def _reasoning_items(first_input):
    return [entry for entry in first_input
            if entry.get("type") == "reasoning"]


def test_replay_arm_replays_reasoning_without_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    job_id = matched.fork_job(_record(), OPTIONS[0], "01:05",
                              tmp_path / "data")
    seen: list = []
    runner.resume_job(job_id, respond_fn=_capture_stub(seen))
    assert seen, "resume made no model call"
    assert len(_reasoning_items(seen[0])) == 1
    assert _input_file_parts(seen[0]) == []


def test_resend_arm_drops_reasoning_and_attaches_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    job_id = matched.fork_job(_record(), OPTIONS[0], "01:05",
                              tmp_path / "data")
    seen: list = []
    deleted: list = []
    summary = matched.resume_with_resend(
        job_id, respond_fn=_capture_stub(seen),
        upload_fn=lambda path: {"id": f"file-{Path(path).stem}"},
        delete_fn=lambda fid: deleted.append(fid))
    assert seen, "resume made no model call"
    assert _reasoning_items(seen[0]) == []
    files = _input_file_parts(seen[0])
    assert len(files) == 2
    assert summary["status"] in ("done", "failed")
    assert sorted(deleted) == ["file-baltic_quote_Q-1187-B",
                               "file-baltic_quote_original"]
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "owner_answer" in kinds


def test_thanks_venue_matcher():
    assert matched.thanks_venue(
        "Thank you for confirming the venue can receive the van.") is True
    assert matched.thanks_venue("A van comes Wed 08-12.") is False
    assert matched.thanks_venue("Thanks, Baltic, for the quote.") is False
    assert matched.thanks_venue("") is False


def test_means_counts_holds_drafts_and_thanks():
    records = [
        {"arm": "replay", "job_id": "a", "input_tokens": 100,
         "cached_tokens": 50, "output_tokens": 10, "seconds": 1.0,
         "usd": 0.01, "hold_passed_gateway": True, "drafts": 3,
         "thanks_venue_runs": 1},
        {"arm": "replay", "job_id": "b", "input_tokens": 200,
         "cached_tokens": 100, "output_tokens": 20, "seconds": 3.0,
         "usd": 0.03, "hold_passed_gateway": False, "drafts": 1,
         "thanks_venue_runs": 0},
    ]
    stats = matched.means(records)
    assert stats["runs"] == 2
    assert stats["mean_input_tokens"] == 150.0
    assert stats["mean_cached_tokens"] == 75.0
    assert stats["holds_passed"] == 1
    assert stats["mean_drafts"] == 2.0
    assert stats["thanks_venue_runs"] == 1
    assert stats["job_ids"] == ["a", "b"]


def test_render_report_names_arms_and_jobs():
    payload = {
        "recorded_job_id": "rec-matched-1", "answer": OPTIONS[0],
        "answer_vt": "01:05", "model": "muse-spark-1.3",
        "effort": "medium", "started_utc": "2026-10-28T00:00:00+00:00",
        "records": [], "means": {
            "replay": {"runs": 0, "mean_input_tokens": 0,
                       "mean_cached_tokens": 0, "mean_output_tokens": 0,
                       "mean_seconds": 0, "mean_usd": 0, "holds_passed": 0,
                       "mean_drafts": 0, "thanks_venue_runs": 0,
                       "job_ids": []},
            "resend": {"runs": 0, "mean_input_tokens": 0,
                       "mean_cached_tokens": 0, "mean_output_tokens": 0,
                       "mean_seconds": 0, "mean_usd": 0, "holds_passed": 0,
                       "mean_drafts": 0, "thanks_venue_runs": 0,
                       "job_ids": []}},
    }
    report = matched.render_report(payload)
    assert "rec-matched-1" in report
    assert "| replay |" in report and "| resend |" in report
