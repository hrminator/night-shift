"""Contract tests 1 and 2 (pure code, no model).

1: an approval covers one exact version (content + recipient), once; editing
   the draft voids it; approving an outdated hash is refused.
2: an approval is valid 30 minutes after it is given on the virtual clock,
   or until the item's own deadline, whichever is first. The Vestland order
   draft lapses with the hold at 09:00, so approving it at 09:01 is refused
   with "hold lapsed". Approved drafts move to the simulated outbox as
   `delivered` events labelled "Simulated delivery".
"""

from __future__ import annotations

import urllib.parse

from fastapi.testclient import TestClient

import app.main as main_mod
from app import gateway
from app.store import append_event, create_job, list_events


def _seed():
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    append_event(job["id"], "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    return job["id"]


def _propose(job_id, purpose="order", body="Exact order text."):
    result = gateway.check_propose_message(
        job_id,
        {"to": "Vestland Tekstil", "subject": "Order H-2041", "body": body,
         "purpose": purpose}, "01:10")
    assert result["ok"] is True
    return result["draft_id"]


def _head(job_id, draft_id):
    event = next(e for e in list_events(job_id) if e["id"] == draft_id)
    return gateway.draft_head(job_id, gateway.draft_key_of(event))


def test_approve_exact_version_then_edit_voids(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id)
    head = _head(job_id, draft_id)
    version_hash = gateway.head_version_hash(head)
    approved = gateway.approve_draft(job_id, head["id"], version_hash,
                                     "07:00")
    assert approved["ok"] is True
    stored = next(e for e in list_events(job_id)
                  if e["kind"] == "approval")
    assert stored["payload"]["version_hash"] == version_hash
    delivered = gateway.deliver_approved(job_id, approved["approval_id"],
                                         "07:00")
    assert delivered["ok"] is True
    out = next(e for e in list_events(job_id) if e["kind"] == "delivered")
    assert out["payload"]["outbox"] == "Simulated delivery"
    edited = gateway.edit_draft(job_id, head["id"],
                                "Exact order text, one word changed.",
                                "07:05")
    assert edited["ok"] is True
    valid, reason = gateway.approval_valid_at(
        job_id, approved["approval_id"], "07:05")
    assert valid is False
    assert reason == "draft edited"
    stale = gateway.approve_draft(job_id, head["id"], version_hash, "07:06")
    assert stale["ok"] is False
    assert "outdated" in stale["reason"]


def test_approve_outdated_hash_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id)
    head = _head(job_id, draft_id)
    refused = gateway.approve_draft(job_id, head["id"], "0" * 64, "07:00")
    assert refused["ok"] is False
    assert "outdated" in refused["reason"]
    assert "approval" not in [e["kind"] for e in list_events(job_id)]


def test_approve_order_after_lapse_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id)
    head = _head(job_id, draft_id)
    version_hash = gateway.head_version_hash(head)
    late = gateway.approve_draft(job_id, head["id"], version_hash, "09:01")
    assert late["ok"] is False
    assert late["reason"] == "hold lapsed"
    on_time = gateway.approve_draft(job_id, head["id"], version_hash,
                                     "09:00")
    assert on_time["ok"] is True


def test_approval_expires_after_30_minutes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id, purpose="venue_note", body="Van Wed 08-12.")
    head = _head(job_id, draft_id)
    approved = gateway.approve_draft(job_id, head["id"],
                                     gateway.head_version_hash(head),
                                     "07:00")
    assert approved["ok"] is True
    valid, _ = gateway.approval_valid_at(job_id, approved["approval_id"],
                                         "07:30")
    assert valid is True
    assert gateway.deliver_approved(job_id, approved["approval_id"],
                                    "07:15")["ok"] is True
    late = gateway.deliver_approved(job_id, approved["approval_id"], "07:31")
    assert late["ok"] is False
    assert late["reason"] == "approval expired"


def test_deliver_is_once_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id, purpose="venue_note", body="Van Wed 08-12.")
    head = _head(job_id, draft_id)
    approved = gateway.approve_draft(job_id, head["id"],
                                     gateway.head_version_hash(head),
                                     "07:00")
    assert gateway.deliver_approved(job_id, approved["approval_id"],
                                    "07:00")["ok"] is True
    again = gateway.deliver_approved(job_id, approved["approval_id"],
                                     "07:01")
    assert again["ok"] is False
    assert again["reason"] == "already delivered"


def _form(**fields):
    return urllib.parse.urlencode(fields)


def test_morning_approve_edit_flips_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    draft_id = _propose(job_id)
    head = _head(job_id, draft_id)
    version_hash = gateway.head_version_hash(head)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        f"/jobs/{job_id}/approve",
        content=_form(draft_id=head["id"], version_hash=version_hash),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "approved" in client.get(f"/jobs/{job_id}/morning").text
    response = client.post(
        f"/jobs/{job_id}/edit-draft",
        content=_form(draft_id=head["id"],
                      body="Exact order text, one word changed."),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    morning = client.get(f"/jobs/{job_id}/morning").text
    assert "needs approval again" in morning
    response = client.post(
        f"/jobs/{job_id}/approve",
        content=_form(draft_id=head["id"], version_hash=version_hash),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 400
