"""Contract tests 3, 4, 5 (pure code, no model).

3: the owner's factual answer alone never places a hold or sends anything.
4: a hold outside the permission is refused.
5: double submit and retries never create a second effect.
Plus: without the permission the hold becomes an approval item, not an effect.
"""

from __future__ import annotations

import pytest

from app import gateway
from app import portal as portal_mod
from app.store import append_event, create_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
BRIEFLESS = "Job: 100 tote bags. No standing permission in this brief."


def _seed(brief_text: str | None = None):
    job = create_job(status="running", current_step="waiting_for_owner",
                     virtual_time="00:47")
    handoff = {"brief": "fixtures/brief.md", "source": "owner"}
    if brief_text is not None:
        handoff["brief_text"] = brief_text
    append_event(job["id"], "21:30", "handoff", handoff)
    return job["id"]


def _answer(job_id: str, virtual_time: str = "01:05"):
    return append_event(job_id, virtual_time, "owner_answer",
                        {"choice": "Bergen: the venue can receive it",
                         "source": "owner"})


def _fields(answer_id: int, **overrides):
    fields = {
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
    }
    fields.update(overrides)
    return fields


def _args(answer_id: int, **overrides):
    return {"portal": "Vestland Tekstil", "fields": _fields(answer_id,
                                                            **overrides)}


def _kinds(job_id: str) -> list[str]:
    return [e["kind"] for e in list_events(job_id)]


def test_valid_hold_passes_with_four_records(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    answer = _answer(job_id)
    result = gateway.check_submit_hold(job_id, _args(answer["id"]), "01:05")
    assert result["ok"] is True
    assert "H-2041" in result["acknowledgement"]
    assert "Simulated supplier system" in result["acknowledgement"]
    kinds = _kinds(job_id)
    for kind in ("owner_answer", "permission_used", "gateway_result",
                 "effect"):
        assert kind in kinds
    checks = [e for e in list_events(job_id) if e["kind"] == "gateway_check"]
    assert [c["payload"]["check"] for c in checks] == gateway.CHECK_ORDER
    assert all(c["payload"]["passed"] for c in checks)


def test_answer_alone_creates_no_effect(tmp_path, monkeypatch):
    """Contract 3: a factual answer, without the permission, does nothing."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed(brief_text=BRIEFLESS)
    _answer(job_id)
    assert "effect" not in _kinds(job_id)
    assert "draft" not in _kinds(job_id)


def test_hold_without_permission_becomes_approval_item(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed(brief_text=BRIEFLESS)
    answer = _answer(job_id)
    result = gateway.check_submit_hold(job_id, _args(answer["id"]), "01:05")
    assert result["ok"] is False
    assert result["check"] == "permission"
    events = list_events(job_id)
    assert "attempt_refused" in [e["kind"] for e in events]
    assert "effect" not in [e["kind"] for e in events]
    drafts = [e for e in events if e["kind"] == "draft"]
    assert len(drafts) == 1
    assert drafts[0]["payload"]["status"] == "awaiting_approval"
    assert drafts[0]["payload"]["purpose"] == "hold_request"


def _refused_case(extra_args=None, answer_vt="01:05", submit_vt="01:05",
                  field_overrides=None, brief_text=None):
    import copy
    job_id = _seed(brief_text=brief_text)
    answer = _answer(job_id, virtual_time=answer_vt)
    args = copy.deepcopy(extra_args) if extra_args is not None else None
    if args is None:
        args = _args(answer["id"], **(field_overrides or {}))
    return job_id, gateway.check_submit_hold(job_id, args, submit_vt)


@pytest.mark.parametrize("label,make_args", [
    ("wrong portal", lambda aid: {"portal": "Baltic Print",
                                  "fields": _fields(aid)}),
    ("extra field", lambda aid: {"portal": "Vestland Tekstil",
                                 "fields": _fields(aid, courier="overnight")}),
    ("cost above 0", lambda aid: {"portal": "Vestland Tekstil",
                                  "fields": _fields(aid, cost=400)}),
    ("binding terms", lambda aid: {"portal": "Vestland Tekstil",
                                   "fields": _fields(aid, binding=True)}),
    ("hold ends late", lambda aid: {"portal": "Vestland Tekstil",
                                    "fields": _fields(aid,
                                                      hold_ends="10:00")}),
    ("wrong quantity", lambda aid: {"portal": "Vestland Tekstil",
                                    "fields": _fields(aid, quantity=50)}),
    ("unlisted address", lambda aid: {"portal": "Vestland Tekstil",
                                      "fields": _fields(
                                          aid, address="Tallinn depot")}),
    ("budget leaks", lambda aid: {"portal": "Vestland Tekstil",
                                  "fields": _fields(
                                      aid, ordering_contact="owner, "
                                      "budget NOK 3500")}),
    ("other supplier leaks", lambda aid: {"portal": "Vestland Tekstil",
                                          "fields": _fields(
                                              aid, product="tote bags, "
                                              "Nordtrykk NOK 22")}),
    ("unverified source", lambda aid: {"portal": "Vestland Tekstil",
                                       "fields": _fields(aid, sources={
                                           "recipient_can_receive": 9999,
                                           "route": "vestland_portal.json v1",
                                           "window":
                                           "vestland_portal.json v1"})}),
])
def test_hold_outside_permission_refused(tmp_path, monkeypatch, label,
                                         make_args):
    """Contract 4: each violation is refused and logs attempt_refused."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    answer = _answer(job_id)
    result = gateway.check_submit_hold(job_id, make_args(answer["id"]),
                                       "01:05")
    assert result["ok"] is False, label
    events = list_events(job_id)
    assert "attempt_refused" in [e["kind"] for e in events], label
    assert "effect" not in [e["kind"] for e in events], label


def test_late_answer_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _job_id, result = _refused_case(answer_vt="02:05")
    assert result["ok"] is False
    assert result["check"] == "time"


def test_late_submit_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _job_id, result = _refused_case(submit_vt="02:01")
    assert result["ok"] is False
    assert result["check"] == "time"


def test_second_hold_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    answer = _answer(job_id)
    first = gateway.check_submit_hold(job_id, _args(answer["id"]), "01:05")
    assert first["ok"] is True
    changed = _args(answer["id"], ordering_contact="deputy")
    second = gateway.check_submit_hold(job_id, changed, "01:06")
    assert second["ok"] is False
    assert second["check"] == "once-only"
    effects = [e for e in list_events(job_id) if e["kind"] == "effect"]
    assert len(effects) == 1


def test_double_submit_creates_one_effect(tmp_path, monkeypatch):
    """Contract 5: identical retries return the record and create nothing."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    answer = _answer(job_id)
    args = _args(answer["id"])
    first = gateway.check_submit_hold(job_id, args, "01:05")
    assert first["ok"] is True
    count_before = len(list_events(job_id))
    second = gateway.check_submit_hold(job_id, args, "01:05")
    assert second["ok"] is True
    assert second.get("deduped") is True
    assert second["operation_id"] == first["operation_id"]
    assert second["effect_event_id"] == first["effect_event_id"]
    assert len(list_events(job_id)) == count_before
    effects = [e for e in list_events(job_id) if e["kind"] == "effect"]
    assert len(effects) == 1


def test_portal_retry_returns_existing_record(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    operation_id = gateway.operation_id_for(job_id, "submit_hold",
                                            {"portal": "Vestland Tekstil",
                                             "fields": {"quantity": 100}})
    first = portal_mod.ensure_hold(job_id, operation_id, "01:05",
                                   "Vestland Tekstil", {"quantity": 100})
    second = portal_mod.ensure_hold(job_id, operation_id, "01:05",
                                    "Vestland Tekstil", {"quantity": 100})
    assert first["deduped"] is False
    assert second["deduped"] is True
    assert second["effect_event_id"] == first["effect_event_id"]
    effects = [e for e in list_events(job_id) if e["kind"] == "effect"]
    assert len(effects) == 1


def test_propose_message_creates_draft_never_sends(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    result = gateway.check_propose_message(
        job_id,
        {"to": "Vestland Tekstil", "subject": "Order?", "body": "Exact text.",
         "purpose": "order"}, "01:10")
    assert result["ok"] is True
    events = list_events(job_id)
    drafts = [e for e in events if e["kind"] == "draft"]
    assert len(drafts) == 1
    assert drafts[0]["payload"]["status"] == "awaiting_approval"
    assert drafts[0]["payload"]["body"] == "Exact text."
    assert "effect" not in [e["kind"] for e in events]
