"""Notes to you sit above the letters; Needs you counts current externals.

Drafts addressed to the owner render under "Notes to you" above the
"Needs you" letters and are excluded from its count. "Needs you: N
approvals" equals the number of current letters to outside parties, on
the pinned exports and on a synthetic night with a superseded recipient.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import app.main as main_mod
from app import gateway
from app.store import append_event, create_job, list_events

ROOT = Path(__file__).resolve().parent.parent


def _docker_pins():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    hero = re.search(r'RECORDED_JOB="([0-9a-f]+)"', text).group(1)
    night_b = re.search(r'RECORDED_JOB_B="([0-9a-f]+)"', text).group(1)
    return hero, night_b


def _needs_you_count(page: str) -> int:
    match = re.search(r"Needs you: (\d+) approval", page)
    assert match is not None, page[:2000]
    return int(match.group(1))


def _needs_letters(page: str) -> int:
    part = page.split("<h2>Needs you:", 1)[1].split("</section>", 1)[0]
    return part.count('data-draft="') + part.count("SIMULATED DELIVERY")


def test_count_equals_cards_on_both_pins():
    hero, night_b = _docker_pins()
    for job_id in (hero, night_b):
        record = json.loads(
            (ROOT / "data" / "runs" / f"job-{job_id}.json").read_text(
                encoding="utf-8"))
        events = record["events"]
        page = main_mod.render_morning_page(f"Job {job_id}", events,
                                            job_id=None)
        count = _needs_you_count(page)
        assert count == len(main_mod._approval_heads(events)), job_id
        assert count == _needs_letters(page), job_id
        assert "<h2>Notes to you</h2>" in page, job_id
        assert page.index("<h2>Notes to you</h2>") < page.index(
            "<h2>Needs you:"), job_id


def test_count_equals_cards_with_superseded_recipient(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    gateway.check_propose_message(job_id, {
        "to": "supplier-a@example.com", "subject": "Early order",
        "body": "Order the early plan.", "purpose": "early_plan"},
        "22:30")
    gateway.check_propose_message(job_id, {
        "to": "owner@fjord-fern.example.com", "subject": "Early note",
        "body": "Early comparison.", "purpose": "early_note"},
        "22:30")
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    gateway.check_propose_message(job_id, {
        "to": "supplier-a@example.com", "subject": "Current plan",
        "body": "The plan changed; here is the current text.",
        "purpose": "current_plan"}, "01:05")
    gateway.check_propose_message(job_id, {
        "to": "supplier-b@example.com", "subject": "Other supplier",
        "body": "Unchanged other message.", "purpose": "other"}, "01:05")
    gateway.check_propose_message(job_id, {
        "to": "owner@fjord-fern.example.com", "subject": "Current note",
        "body": "Current comparison.", "purpose": "current_note"},
        "01:05")
    append_event(job_id, "01:05", "effect", {
        "tool": "submit_hold", "operation_id": "op-notes",
        "hold_id": "H-2041", "portal": "vestland_portal",
        "acknowledgement": "Vestland Tekstil · Hold H-2041 · "
                           "Simulated supplier system"})
    events = list_events(job_id)
    smap = gateway.superseded_map(job_id)
    early = [e for e in events
             if (e.get("payload") or {}).get("subject") == "Early order"][0]
    assert smap[early["id"]] == "superseded"
    assert len(main_mod._approval_heads(events)) == 2
    assert len(main_mod._for_you_heads(events)) == 1
    page = main_mod.render_morning_page(f"Job {job_id}", events,
                                        job_id=job_id)
    assert _needs_you_count(page) == 2
    assert page.count("Approve this exact text") == 2
    assert "<h2>Notes to you</h2>" in page
    assert page.index("<h2>Notes to you</h2>") < page.index(
        "<h2>Needs you:")
    assert "Early order" in page.split("Earlier versions", 1)[1]
