"""Two arms (pure code): supervision enforces the four rules, direct does not.

Supervision: after a new source event the app asks for a re-assessment;
ask_owner requires the six checks plus a wake decision; the app supplies
computed deadline facts; a question with no decision record is refused.
Direct: same brief, permission, wake rule, model, effort, tools and gateway,
but none of the four rules is enforced.
"""

from __future__ import annotations

import json

from app import runner
from app.store import append_event, create_job, list_events

ASK_ARGS = {
    "question": "Can the venue receive Wed 08-12?",
    "why_now": "cutoff near", "what_checked": "sources",
    "if_yes": "hold", "if_no": "no hold",
    "options": ["Bergen: the venue can receive it", "No / not sure"],
}


def _call(name, args, call_id="c1"):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _seed_post_event_job():
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    return job_id


def test_direct_ask_owner_never_refused_for_missing_checks():
    job_id = _seed_post_event_job()
    out = runner.execute_tool_call(
        job_id, _call("ask_owner", ASK_ARGS), "00:39", arm="direct")
    assert json.loads(out["output"])["stored"] is True
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "question" in kinds
    assert "tool_refused" not in kinds


def test_supervision_ask_owner_refused_for_missing_checks():
    job_id = _seed_post_event_job()
    out = runner.execute_tool_call(
        job_id, _call("ask_owner", ASK_ARGS), "00:39",
        arm="supervision")
    assert "refused" in out["output"]
    kinds = [e["kind"] for e in list_events(job_id)]
    assert "question" not in kinds
    assert "tool_refused" in kinds


def test_direct_instructions_carry_no_deadline_facts_or_gate():
    hero = runner.build_reassess_instructions("supervision")
    direct = runner.build_reassess_instructions("direct")
    assert "latest safe notification 01:30" in hero
    assert "refused in code" in hero
    assert "01:30" not in direct
    assert "01:50" not in direct
    assert "02:00" not in direct or "portal record states its cutoff" in direct
    assert "refused in code" not in direct
    assert "optional, never required" in direct
    for text in (hero, direct):
        assert "standing permission" in text.lower()
        assert "Evidence rule" in text


def test_direct_resume_instructions_carry_no_deadline_facts():
    job = create_job(virtual_time="01:05")
    answer = append_event(job["id"], "01:05", "owner_answer",
                          {"choice": "yes", "source": "owner"})
    hero = runner.build_resume_instructions(job["id"], answer, "supervision")
    direct = runner.build_resume_instructions(job["id"], answer, "direct")
    assert "computed by code" in hero
    assert "computed by code" not in direct
    assert "portal record states its cutoff" in direct


def test_run_turn_threads_arm_to_ask_owner():
    for arm, want_question in (("direct", True), ("supervision", False)):
        job_id = _seed_post_event_job()
        script = [
            {"output": [_call("ask_owner", ASK_ARGS, "c1")], "text": ""},
            {"output": [{"type": "message", "content": [
                {"type": "output_text", "text": "done"}]}], "text": "done"},
        ]
        state = {"n": 0}

        def stub(instructions, input_items, **kwargs):
            item = script[state["n"]]
            state["n"] += 1
            return item

        runner.run_turn(job_id, "instructions", [{"t": 0}],
                        runner.REASSESS_TOOLS, stub, "00:39", arm=arm)
        kinds = [e["kind"] for e in list_events(job_id)]
        assert ("question" in kinds) is want_question


def test_gateway_same_for_both_arms():
    for arm in ("supervision", "direct"):
        job_id = _seed_post_event_job()
        out = runner.execute_tool_call(
            job_id, _call("submit_hold", {"portal": "x"}, "c9"),
            "00:39", arm=arm)
        assert "schema" in out["output"]
        kinds = [e["kind"] for e in list_events(job_id)]
        assert "tool_malformed" in kinds
        assert "gateway_check" not in kinds
