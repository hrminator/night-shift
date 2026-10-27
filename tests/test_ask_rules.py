"""One-question and ask-deadline rules for the supervision arm (pure code).

Part 1: a second ask_owner about the same fact is refused in code with
``ask_refused_duplicate``; a different fact needs ``ref_question``.
Part 2: ask_owner past the answer deadline is refused in code with
``ask_refused_too_late``. The direct arm enforces neither rule.
"""

from __future__ import annotations

import json

from app import runner
from app.store import append_event, create_job, list_events

ASK_ARGS = {
    "question": "Can Sjosalen receive the van Wed Nov 11 08:00-12:00?",
    "why_now": "cutoff near", "what_checked": "sources",
    "if_yes": "hold", "if_no": "no hold",
    "options": ["Yes - can receive", "No - cannot"],
}


def _call(name, args, call_id="c1"):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _seed_ready_job(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:38", "revised_quote",
                 {"quote": "Q-1187-B", "replaces": "Q-1187"})
    for name in runner.CHECK_NAMES:
        append_event(job_id, "00:41", "check",
                     {"name": name, "result": "fail", "evidence": [],
                      "note": "stub"})
    append_event(job_id, "00:46", "decision",
                 {"outcome": "wake", "reason": "stub", "evidence": []})
    return job_id


def _ask(job_id, args, virtual_time, arm="supervision", call_id="c1"):
    out = runner.execute_tool_call(
        job_id, _call("ask_owner", args, call_id), virtual_time, arm=arm)
    return json.loads(out["output"])


def _kinds(job_id):
    return [e["kind"] for e in list_events(job_id)]


def test_second_identical_question_refused(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    first = _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    assert first["stored"] is True
    second = _ask(job_id, ASK_ARGS, "00:48", call_id="c2")
    assert "refused" in second["error"]
    assert "Can Sjosalen receive" in second["error"]
    kinds = _kinds(job_id)
    assert "ask_refused_duplicate" in kinds
    assert sum(1 for kind in kinds if kind == "question") == 1


def test_duplicate_refusal_quotes_the_answer(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    runner.store_answer(job_id, "Bergen: the venue can receive it", "01:05")
    second = _ask(job_id, ASK_ARGS, "01:06", call_id="c2")
    assert "refused" in second["error"]
    assert "Bergen: the venue can receive it" in second["error"]
    assert "ask_refused_duplicate" in _kinds(job_id)


def test_same_target_reworded_refused(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    _ask(job_id, {**ASK_ARGS, "target": "venue_receipt"}, "00:47",
         call_id="c1")
    reworded = {**ASK_ARGS, "target": "venue_receipt",
                "question": "Is somebody at Sjosalen to take the van?"}
    second = _ask(job_id, reworded, "00:48", call_id="c2")
    assert "refused" in second["error"]
    assert "ask_refused_duplicate" in _kinds(job_id)


def test_different_fact_with_ref_allowed(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    first = _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    other = {
        "question": "Which ordering contact goes on the hold?",
        "why_now": "form needs it", "what_checked": "studio file",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Use the standard contact", "I will type it"],
        "ref_question": first["question_id"],
    }
    second = _ask(job_id, other, "00:48", call_id="c2")
    assert second.get("stored") is True
    assert sum(1 for kind in _kinds(job_id) if kind == "question") == 2


def test_different_fact_without_ref_refused(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    other = {
        "question": "Which ordering contact goes on the hold?",
        "why_now": "form needs it", "what_checked": "studio file",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Use the standard contact", "I will type it"],
    }
    second = _ask(job_id, other, "00:48", call_id="c2")
    assert "refused" in second["error"]
    assert "ref_question" in second["error"]
    assert "ask_refused_duplicate" in _kinds(job_id)


def test_same_fact_with_ref_still_refused(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    first = _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    retry = {**ASK_ARGS, "ref_question": first["question_id"]}
    second = _ask(job_id, retry, "00:48", call_id="c2")
    assert "refused" in second["error"]
    assert "ask_refused_duplicate" in _kinds(job_id)


def test_direct_arm_allows_repeat_questions(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    first = _ask(job_id, ASK_ARGS, "00:47", arm="direct", call_id="c1")
    second = _ask(job_id, ASK_ARGS, "00:48", arm="direct", call_id="c2")
    assert first["stored"] is True
    assert second["stored"] is True
    assert "ask_refused_duplicate" not in _kinds(job_id)


def test_ask_after_deadline_refused(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    out = _ask(job_id, ASK_ARGS, "02:30", call_id="c1")
    assert "refused" in out["error"]
    assert "01:50" in out["error"]
    assert "wait_for_morning" in out["error"]
    kinds = _kinds(job_id)
    assert "ask_refused_too_late" in kinds
    assert "question" not in kinds


def test_ask_at_deadline_allowed(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    out = _ask(job_id, ASK_ARGS, "01:50", call_id="c1")
    assert out.get("stored") is True


def test_direct_arm_ignores_deadline(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    out = _ask(job_id, ASK_ARGS, "02:30", arm="direct", call_id="c1")
    assert out.get("stored") is True
    assert "ask_refused_too_late" not in _kinds(job_id)


def test_deadline_follows_the_nights_own_cutoff(monkeypatch, tmp_path):
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    original = runner.fixture_text

    def fake_text(name):
        if name == "vestland_portal.json":
            return ('{"hold_rules": {"requests_close": "10:00 '
                    '(scenario clock)"}}')
        return original(name)

    monkeypatch.setattr(runner, "fixture_text", fake_text)
    late = _ask(job_id, ASK_ARGS, "09:55", call_id="c1")
    assert "refused" in late["error"]
    assert "09:50" in late["error"]
    assert "01:50" not in late["error"]


def test_scorer_counts_prevented_duplicates(monkeypatch, tmp_path):
    from app import eval_score
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    _ask(job_id, ASK_ARGS, "00:47", call_id="c1")
    _ask(job_id, ASK_ARGS, "00:48", call_id="c2")
    seen = eval_score.observed(list_events(job_id))
    assert seen["notifications"] == 1
    assert seen["duplicates_prevented"] == 1
    summary = eval_score.summarize([{
        "case_type": "decision_only",
        "case_predicates": {"notified": True},
        "observed": {**seen, "notified": True, "notified_at": "00:47",
                     "claims_missing_source": 0, "attempts_refused": 0,
                     "effects": 0},
        "pass": True, "usd": 0.1, "seconds": 10.0}])
    assert summary["duplicates_prevented"] == 1
    assert summary["duplicate_notifications"] == 0


def test_scorer_counts_too_late_refusals(monkeypatch, tmp_path):
    from app import eval_score
    job_id = _seed_ready_job(monkeypatch, tmp_path)
    _ask(job_id, ASK_ARGS, "02:30", call_id="c1")
    seen = eval_score.observed(list_events(job_id))
    assert seen["notified"] is False
    assert seen["asks_refused_too_late"] == 1
