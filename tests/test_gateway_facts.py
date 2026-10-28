"""F4b part 1: the gateway asserts facts, not pointers (pure code, no model).

A hold's "recipient can receive" must cite either an owner_answer that says
yes to the receiving question, or a venue claim whose quote states receipt
in the van window. The permission comes from a parsed record, never from
matching words in the brief at check time.
"""

from __future__ import annotations

from app import gateway
from app import permission as permission_mod
from app.store import append_event, create_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
CONTACT = ("Kari Strandli, studio coordinator,"
           " orders@fjord-fern.example.com, +47 22 00 11 22")
PRINT_FILE = "fjord-fern-logo-print.pdf"
YES = "Bergen: the venue can receive it"
NO = "No / not sure"

RECEIVING_QUESTION = {
    "question": "Can Sjøsalen, Bergen receive the 100 tote bags Wed Nov 11"
                " 08:00-12:00?",
    "why_now": "cutoff 02:00",
    "what_checked": "all six checks",
    "if_yes": "one hold",
    "if_no": "no hold",
    "options": [YES, NO],
}

CONTACT_QUESTION = {
    "question": "What ordering contact should I put on the Vestland hold?",
    "why_now": "contact missing",
    "what_checked": "studio file",
    "if_yes": "hold",
    "if_no": "no hold",
    "options": ["Use standard ordering contact on file for the hold",
                "I will type the exact contact name/email to use now"],
}

THURSDAY_QUOTE = ("This confirmation covers the Thursday event only. It says"
                  " nothing about deliveries on other days.")
WEDNESDAY_QUOTE = ("Deliveries for your event can be received Wed Nov 11,"
                   " 08:00-16:00 at the goods entrance.")

NO_PERMISSION_BRIEF = """# Evening brief

> **Job:** 100 tote bags.
> **Everything else that leaves the building** waits for my OK.
"""


def _seed(brief_text=None):
    job = create_job(status="running", current_step="waiting_for_owner",
                     virtual_time="00:47")
    handoff = {"brief": "fixtures/brief.md", "source": "owner"}
    if brief_text is not None:
        handoff["brief_text"] = brief_text
    append_event(job["id"], "21:30", "handoff", handoff)
    return job["id"]


def _question(job_id, payload):
    return append_event(job_id, "00:47", "question", payload)


def _answer(job_id, choice, virtual_time="01:05"):
    return append_event(job_id, virtual_time, "owner_answer",
                        {"choice": choice, "source": "owner"})


def _claim(job_id, source, quote):
    return append_event(job_id, "22:30", "claim",
                        {"source": source, "quote": quote,
                         "claim": "seeded"})


def _hold_args(recipient_kind, recipient_id):
    return {
        "portal": "vestland_portal",
        "action": "capacity_hold",
        "product": "100 tote bags with logo",
        "quantity": 100,
        "print_file": PRINT_FILE,
        "address": VENUE_ADDRESS,
        "delivery_window": "Wed Nov 11 08:00-12:00",
        "ordering_contact": CONTACT,
        "recipient_can_receive": True,
        "cost": 0,
        "binding": False,
        "hold_ends": "09:00",
        "sources": {
            "recipient_can_receive": {"kind": recipient_kind,
                                      "id": recipient_id},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"},
        },
    }


def test_no_answer_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    _question(job_id, RECEIVING_QUESTION)
    answer = _answer(job_id, NO)
    result = gateway.check_submit_hold(
        job_id, _hold_args("owner_answer", answer["id"]), "01:05")
    assert result["ok"] is False
    assert result["check"] == "sources"
    assert "no" in result["reason"].lower()
    assert "effect" not in [e["kind"] for e in list_events(job_id)]


def test_yes_to_a_different_question_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    _question(job_id, CONTACT_QUESTION)
    answer = _answer(job_id, CONTACT_QUESTION["options"][0])
    result = gateway.check_submit_hold(
        job_id, _hold_args("owner_answer", answer["id"]), "01:05")
    assert result["ok"] is False
    assert result["check"] == "sources"
    assert "effect" not in [e["kind"] for e in list_events(job_id)]


def test_yes_choice_without_a_receiving_question_is_refused(tmp_path,
                                                            monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    _question(job_id, CONTACT_QUESTION)
    answer = _answer(job_id, YES)
    result = gateway.check_submit_hold(
        job_id, _hold_args("owner_answer", answer["id"]), "01:05")
    assert result["ok"] is False
    assert result["check"] == "sources"


def test_thursday_only_venue_claim_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    claim = _claim(job_id, "venue confirmation", THURSDAY_QUOTE)
    result = gateway.check_submit_hold(
        job_id, _hold_args("claim", claim["id"]), "22:30")
    assert result["ok"] is False
    assert result["check"] == "sources"
    assert "effect" not in [e["kind"] for e in list_events(job_id)]


def test_wednesday_venue_claim_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    claim = _claim(job_id, "venue confirmation", WEDNESDAY_QUOTE)
    result = gateway.check_submit_hold(
        job_id, _hold_args("claim", claim["id"]), "22:30")
    assert result["ok"] is True


def test_hero_path_still_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    _question(job_id, RECEIVING_QUESTION)
    answer = _answer(job_id, YES)
    result = gateway.check_submit_hold(
        job_id, _hold_args("owner_answer", answer["id"]), "01:05")
    assert result["ok"] is True
    checks = [e for e in list_events(job_id)
              if e["kind"] == "gateway_check"]
    assert [c["payload"]["check"] for c in checks] == gateway.CHECK_ORDER
    sources = next(c for c in checks
                   if c["payload"]["check"] == "sources")
    assert "answered yes" in sources["payload"]["detail"]
    assert "01:05" in sources["payload"]["detail"]


def test_brief_without_permission_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed(brief_text=NO_PERMISSION_BRIEF)
    _question(job_id, RECEIVING_QUESTION)
    answer = _answer(job_id, YES)
    result = gateway.check_submit_hold(
        job_id, _hold_args("owner_answer", answer["id"]), "01:05")
    assert result["ok"] is False
    assert result["check"] == "permission"
    assert "no permission in brief" in result["reason"]
    assert "effect" not in [e["kind"] for e in list_events(job_id)]


def test_permission_record_parsed_once(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id = _seed()
    _question(job_id, RECEIVING_QUESTION)
    answer = _answer(job_id, YES)
    args = _hold_args("owner_answer", answer["id"])
    assert gateway.check_submit_hold(job_id, args, "01:05")["ok"] is True
    parsed = [e for e in list_events(job_id)
              if e["kind"] == "permission_parsed"]
    assert len(parsed) == 1
    payload = parsed[0]["payload"]
    assert payload["action"] == "reservation_hold"
    assert payload["supplier"] == "vestland"
    assert payload["max_cost"] == 0
    assert payload["cutoff"] == "02:00"
    assert payload["required_fact"] == "recipient_can_receive"
    assert payload["version"]
    # A retry reads the same record; nothing is parsed again.
    gateway.check_submit_hold(job_id, args, "01:05")
    assert len([e for e in list_events(job_id)
                if e["kind"] == "permission_parsed"]) == 1


def test_parse_permission_marks_a_missing_box(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    record = permission_mod.parse_permission("Job: 100 tote bags.")
    assert record["action"] == "none"
    assert record["version"]
    assert permission_mod.permission_allows(record) is False
