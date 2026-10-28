"""Submit-hold tool contract: explicit schema, named refusals, turn budget.

The flat payload (portal, action, product, ..., sources with kind/id
pointers) is the only shape the tool path accepts. A payload failing the
schema is refused as tool_malformed before the gateway, naming the exact
property plus its expected shape. The gateway still decides meaning, and a
turn that ends on its budget logs turn_budget.
"""

from __future__ import annotations

import copy
import json

import pytest

from app import gateway, hold_schema, runner
from app.store import append_event, create_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
CONTACT = ("Kari Strandli, studio coordinator, "
           "orders@fjord-fern.example.com, +47 22 00 11 22")


def _payload(answer_or_claim_id: int = 7) -> dict:
    return {
        "portal": "vestland_portal",
        "action": "capacity_hold",
        "product": "100 tote bags with logo",
        "quantity": 100,
        "print_file": "fjord-fern-logo-print.pdf",
        "address": VENUE_ADDRESS,
        "delivery_window": "Wed Nov 11 08:00-12:00",
        "ordering_contact": CONTACT,
        "recipient_can_receive": True,
        "cost": 0,
        "binding": False,
        "hold_ends": "09:00",
        "sources": {
            "recipient_can_receive": {"kind": "owner_answer",
                                      "id": answer_or_claim_id},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"},
        },
    }


def _seed(answer_vt: str = "01:05"):
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:47", "question",
                 {"question": "Can the venue receive Wed 08-12?",
                  "why_now": "cutoff near", "what_checked": "sources",
                  "if_yes": "hold", "if_no": "no hold",
                  "options": ["Bergen: the venue can receive it",
                              "No / not sure"]})
    answer = append_event(job_id, answer_vt, "owner_answer",
                          {"choice": "Bergen: the venue can receive it",
                           "source": "owner"})
    return job_id, answer["id"]


def _call(name, args, call_id="c1"):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def test_valid_flat_payload_has_no_schema_errors():
    assert hold_schema.hold_schema_errors(_payload()) == []


def test_tool_definition_schema_matches_validator():
    params = runner.SUBMIT_HOLD_TOOL["parameters"]
    assert params is hold_schema.SUBMIT_HOLD_PARAMETERS
    assert set(params["required"]) == set(hold_schema.HOLD_REQUIRED)
    source_props = params["properties"]["sources"]
    assert set(source_props["required"]) == set(hold_schema.SOURCE_REQUIRED)
    for key in hold_schema.HOLD_REQUIRED:
        assert "description" in params["properties"][key], key


@pytest.mark.parametrize("mutate,prop", [
    (lambda p: p.pop("cost"), "cost"),
    (lambda p: p.pop("sources"), "sources"),
    (lambda p: p.update(portal="Vestland Tekstil"), "portal"),
    (lambda p: p.update(action="hold"), "action"),
    (lambda p: p.update(quantity="100"), "quantity"),
    (lambda p: p.update(quantity=50), "quantity"),
    (lambda p: p.update(cost=400), "cost"),
    (lambda p: p.update(binding=True), "binding"),
    (lambda p: p.update(recipient_can_receive=False),
     "recipient_can_receive"),
    (lambda p: p.update(hold_ends="10:00"), "hold_ends"),
    (lambda p: p.update(courier="overnight"), "courier"),
    (lambda p: p["sources"].pop("route"), "sources.route"),
    (lambda p: p["sources"].update(extra={}), "sources.extra"),
    (lambda p: p["sources"].update(
        recipient_can_receive=7), "sources.recipient_can_receive"),
    (lambda p: p["sources"]["route"].update(kind="quote"),
     "sources.route.kind"),
    (lambda p: p["sources"]["route"].update(version="1"),
     "sources.route.version"),
    (lambda p: p["sources"]["ordering_contact"].update(kind="claim"),
     "sources.ordering_contact"),
])
def test_schema_error_names_the_property(tmp_path, monkeypatch, mutate, prop):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    payload = _payload()
    mutate(payload)
    errors = hold_schema.hold_schema_errors(payload)
    assert errors, prop
    assert any(prop in error for error in errors), (prop, errors)
    assert any("expected" in error for error in errors), errors


def test_schema_failure_is_malformed_before_gateway(tmp_path, monkeypatch):
    """Contract 10: a bad payload never reaches the gateway checks."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, _ = _seed()
    payload = _payload()
    del payload["cost"]
    out = runner.execute_tool_call(job_id, _call("submit_hold", payload))
    body = json.loads(out["output"])
    assert "failed the schema" in body["error"]
    assert '"cost"' in body["error"]
    events = list_events(job_id)
    assert events[-1]["kind"] == "tool_malformed"
    assert "gateway_check" not in [e["kind"] for e in events]
    assert "attempt_refused" not in [e["kind"] for e in events]


def test_flat_payload_passes_gateway_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, answer_id = _seed()
    out = runner.execute_tool_call(
        job_id, _call("submit_hold", _payload(answer_id)), "01:05")
    body = json.loads(out["output"])
    assert body["ok"] is True, body
    assert "H-2041" in body["acknowledgement"]


def test_flat_payload_with_venue_claim_source(tmp_path, monkeypatch):
    """Contrast path: recipient cites a venue-confirmation claim, no answer."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    claim = append_event(
        job_id, "22:30", "claim",
        {"source": "Venue booking confirmation",
         "quote": "Deliveries for your event can be received Wed Nov 11,"
         " 08:00-16:00 at the goods entrance."})
    payload = _payload()
    payload["sources"]["recipient_can_receive"] = {"kind": "claim",
                                                   "id": claim["id"]}
    assert hold_schema.hold_schema_errors(payload) == []
    out = runner.execute_tool_call(job_id, _call("submit_hold", payload),
                                   "00:45")
    assert json.loads(out["output"])["ok"] is True


def test_gateway_refusal_names_key_and_shape(tmp_path, monkeypatch):
    """A meaning error still names the key with its one-line shape."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, answer_id = _seed()
    payload = _payload(answer_id)
    payload["address"] = "Tallinn depot"
    result = gateway.check_submit_hold(job_id, payload, "01:05")
    assert result["ok"] is False
    assert result["check"] == "fields"
    assert '"address"' in result["reason"]
    assert "expected" in result["reason"]


def test_legacy_nested_payload_still_passes_gateway(tmp_path, monkeypatch):
    """Direct gateway unit tests keep their nested shape; only the tool
    path enforces the new schema."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job_id, answer_id = _seed()
    args = {"portal": "Vestland Tekstil",
            "fields": {"product": "100 tote bags with logo", "quantity": 100,
                       "print_file": "fjord-fern-logo-print.pdf",
                       "address": VENUE_ADDRESS,
                       "delivery_window": "Wed Nov 11 08:00-12:00",
                       "ordering_contact": CONTACT,
                       "recipient_can_receive": "yes", "cost": 0,
                       "binding": False, "hold_ends": "09:00",
                       "sources": {"recipient_can_receive": answer_id,
                                   "route": "vestland_portal.json v1",
                                   "window": "vestland_portal.json v1"}}}
    assert gateway.check_submit_hold(job_id, args, "01:05")["ok"] is True


def _stub_calls(calls):
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        item = calls[min(state["n"], len(calls) - 1)]
        state["n"] += 1
        return item

    return stub


def test_tool_budget_end_logs_turn_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    job_id = job["id"]
    claim_call = {"output": [_call(
        "record_claim", {"source": "portal",
                         "quote": "van Wed Nov 11 08:00-12:00"}, "c1")],
        "text": ""}
    stub = _stub_calls([claim_call])
    summary = runner.run_turn(job_id, "instructions", [{"t": 0}],
                              runner.READ_TOOLS, stub, "00:39",
                              max_model_calls=16, tool_budget=1)
    assert summary["status"] == "complete"
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "turn_budget" in kinds
    event = next(e for e in list_events(job_id)
                 if e["kind"] == "turn_budget")
    assert event["payload"]["tool_calls"] == 1


def test_model_call_budget_end_logs_turn_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(virtual_time="00:39")
    job_id = job["id"]
    text_only = {"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "thinking aloud"}]}], "text": "x"}
    claim_call = {"output": [_call(
        "record_claim", {"source": "portal", "quote": "van 08-12"}, "c1")],
        "text": ""}
    stub = _stub_calls([claim_call, text_only])
    summary = runner.run_turn(job_id, "instructions", [{"t": 0}],
                              runner.READ_TOOLS, stub, "00:39",
                              max_model_calls=1, tool_budget=16)
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "turn_budget" in kinds
