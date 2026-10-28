"""Morning page shows exactly the approvals it counts.

An approval card is only a current draft head addressed to an external
party. Notes to the owner render in a "For you" section without approve
buttons. Superseded pre-event drafts stay collapsed under "Earlier
versions" and are never counted. The "Needs you" count equals the
number of approval cards.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.main as main_mod
from app import gateway
from app.store import append_event, create_job, list_events


def _seed_mixed():
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    gateway.check_propose_message(job_id, {
        "to": "owner@fjord-fern.example.com",
        "subject": "Overnight comparison",
        "body": "Baltic verified, cheapest.",
        "purpose": "comparison for 07:00 review"}, "22:30")
    gateway.check_propose_message(job_id, {
        "to": "quotes@baltic-print.example.com",
        "subject": "Order Q-1187",
        "body": "Please reserve Q-1187.",
        "purpose": "baltic order pre-event"}, "22:30")
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    gateway.check_propose_message(job_id, {
        "to": "Vestland Tekstil", "subject": "Confirm hold H-2041",
        "body": "Confirming hold H-2041.", "purpose": "order"}, "01:05")
    gateway.check_propose_message(job_id, {
        "to": "booking@sjosalen.example.com",
        "subject": "Van Wed 08-12", "body": "A van comes Wed 08-12.",
        "purpose": "venue_note"}, "01:05")
    gateway.check_propose_message(job_id, {
        "to": "quotes@baltic-print.example.com",
        "subject": "Q-1187-B query", "body": "What is the arrival date?",
        "purpose": "baltic_note"}, "01:05")
    gateway.check_propose_message(job_id, {
        "to": "owner@fjord-fern.example.com",
        "subject": "What changed overnight",
        "body": "Baltic arrival is now unverified.",
        "purpose": "overnight summary"}, "01:05")
    append_event(job_id, "01:05", "effect", {
        "tool": "submit_hold", "operation_id": "op-test",
        "hold_id": "H-2041", "portal": "vestland_portal",
        "acknowledgement": "Vestland Tekstil · Hold H-2041 · "
                           "Simulated supplier system"})
    return job_id


def _needs_you_count(page: str) -> int:
    match = re.search(r"Needs you: (\d+) approval", page)
    assert match is not None, page[:2000]
    return int(match.group(1))


def test_needs_you_count_equals_approval_cards(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed_mixed()
    events = list_events(job_id)
    assert len(main_mod._approval_heads(events)) == 3
    assert len(main_mod._for_you_heads(events)) == 1
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    page = client.get(f"/jobs/{job_id}/morning").text
    assert _needs_you_count(page) == 3
    assert page.count("Approve this exact text") == 3
    assert "<h2>For you</h2>" in page
    assert "What changed overnight" in page
    for_you = page.split("<h2>For you</h2>", 1)[1]
    for_you = for_you.split("<details>", 1)[0]
    assert "Approve this exact text" not in for_you
    assert "Earlier versions" in page
    earlier = page.split("Earlier versions", 1)[1]
    assert "Overnight comparison" in earlier
    assert "Order Q-1187" in earlier
    assert earlier.count("Approve this exact text") == 0


def test_hero_like_three_externals_count_three(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    for to, subject, purpose in [
            ("Vestland Tekstil", "Confirm hold H-2041", "order"),
            ("booking@sjosalen.example.com", "Van Wed 08-12",
             "venue_note"),
            ("quotes@baltic-print.example.com", "Q-1187-B query",
             "baltic_note")]:
        gateway.check_propose_message(job_id, {
            "to": to, "subject": subject, "body": "Exact body.",
            "purpose": purpose}, "01:05")
    append_event(job_id, "01:05", "effect", {
        "tool": "submit_hold", "operation_id": "op-hero",
        "hold_id": "H-2041", "portal": "vestland_portal",
        "acknowledgement": "Vestland Tekstil · Hold H-2041 · "
                           "Simulated supplier system"})
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    page = client.get(f"/jobs/{job_id}/morning").text
    assert _needs_you_count(page) == 3
    assert page.count("Approve this exact text") == 3
    assert "For you" not in page
    assert "Earlier versions" not in page
