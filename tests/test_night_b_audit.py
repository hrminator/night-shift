"""Part 4: the audit view on job pages (pure code, no model).

Every job page shows the policy hash (SHA-256 of the instruction text),
the model id, the effort, and the fixture set hash; Night B jobs also
show the one changed line with its source file name. Night A and Night B
share the policy hash and differ in the fixture hash.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_mod
from app import night_b as night_b_mod
from app import replay as replay_mod
from app.store import append_event, create_job


def test_same_policy_hash_different_fixture_hash():
    hero = night_b_mod.provenance_payload("hero")
    night_b = night_b_mod.provenance_payload("contrast")
    assert hero["policy_hash"] == night_b["policy_hash"]
    assert len(hero["policy_hash"]) == 64
    assert hero["model"] == night_b["model"] == "muse-spark-1.3"
    assert hero["effort"] == night_b["effort"] == "medium"
    assert hero["fixture_hash"] != night_b["fixture_hash"]
    assert hero["changed_line"] is None
    assert night_b["changed_file"] == "venue_confirmation.md"
    assert night_b["changed_line"] == night_b_mod.night_b_sentence()
    assert "Wed Nov 11" in night_b["changed_line"]


def test_job_page_shows_audit_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    hero_job = create_job(status="running", virtual_time="21:30")
    append_event(hero_job["id"], "21:30", "handoff",
                 {"variant": "hero"})
    night_b_mod.log_provenance(hero_job["id"], "hero")
    b_job = create_job(status="running", virtual_time="21:30")
    append_event(b_job["id"], "21:30", "handoff", {"variant": "contrast"})
    night_b_mod.log_provenance(b_job["id"], "contrast")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    hero_page = client.get(f"/jobs/{hero_job['id']}").text
    b_page = client.get(f"/jobs/{b_job['id']}").text
    policy = night_b_mod.policy_hash()
    assert policy in hero_page and policy in b_page
    assert "muse-spark-1.3" in hero_page
    assert "medium" in b_page
    hero_fixtures = night_b_mod.fixture_set_hash("hero")
    b_fixtures = night_b_mod.fixture_set_hash("contrast")
    assert hero_fixtures in hero_page
    assert b_fixtures in b_page
    assert b_fixtures not in hero_page
    assert "venue_confirmation.md" in b_page
    assert night_b_mod.night_b_sentence() in b_page
    assert "Changed line" not in hero_page


def test_job_page_without_provenance_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="running", virtual_time="21:30")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{job['id']}").text
    assert "Audit: not recorded" in body


def test_visitor_copy_carries_hero_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    record = {"job_id": "rec-audit-1", "events": [
        {"id": 1, "virtual_time": "21:30", "kind": "handoff",
         "payload": {"source": "owner", "variant": "hero"}},
        {"id": 2, "virtual_time": "00:47", "kind": "question",
         "payload": {"question": "Can it receive?",
                     "options": ["Yes", "No"]}},
        {"id": 3, "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 2, "next_input": []}},
    ]}
    new_id = replay_mod.copy_job_for_visitor(record, "Yes")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get(f"/jobs/{new_id}").text
    assert night_b_mod.policy_hash() in body
    assert night_b_mod.fixture_set_hash("hero") in body
    assert "Changed line" not in body
