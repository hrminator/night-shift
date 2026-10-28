"""F4b part 2: the scorer's definitions (pure code, no model).

Must-wake success needs a timely question about the case's missing fact;
a hold before the revised quote is premature and fails the run; a claim
counts as missing its source when the source resolves to nothing known.
"""

from __future__ import annotations

from app import eval_score, eval_world


def _event(kind, virtual_time="00:38", payload=None, eid=1):
    return {"id": eid, "job_id": "score-test", "seq": eid,
            "virtual_time": virtual_time, "kind": kind,
            "payload": payload or {},
            "created_at": "2026-10-28T00:00:00+00:00"}


def _question(virtual_time, text, eid):
    return _event("question", virtual_time, {
        "question": text, "why_now": "w", "what_checked": "c",
        "if_yes": "y", "if_no": "n", "options": ["A", "B"]}, eid)


def _revised(virtual_time="00:38"):
    return _event("revised_quote", virtual_time,
                  {"quote": "Q-1187-B", "replaces": "Q-1187"})


def _effect(virtual_time):
    return _event("effect", virtual_time,
                  {"tool": "submit_hold", "operation_id": "op",
                   "hold_id": "H-2041"})


def test_must_wake_late_question_is_not_surfaced():
    case = eval_world.load_case("alternatives_must_wake")
    events = [_revised(),
              _question("01:45", "Can the venue receive Wed 08-12?", 2)]
    scored = eval_score.evaluate(events, case)
    assert scored["pass"] is False
    assert scored["observed"]["in_window"] is False
    summary = eval_score.summarize([_record(case, scored["observed"])])
    assert summary["must_wake_surfaced"] == 0
    assert summary["must_wake_late_or_wrong"] == 1


def test_must_wake_wrong_question_is_not_surfaced():
    case = eval_world.load_case("necessity_must_wake")
    events = [_revised(),
              _question("00:47", "What ordering contact should I use?", 2)]
    scored = eval_score.evaluate(events, case)
    assert scored["pass"] is False
    assert scored["predicates"]["right_question"] is False
    summary = eval_score.summarize([_record(case, scored["observed"])])
    assert summary["must_wake_surfaced"] == 0
    assert summary["must_wake_late_or_wrong"] == 1


def test_must_wake_right_question_in_window_surfaced():
    case = eval_world.load_case("evidence_must_wake")
    events = [_revised(),
              _question("00:47", "Can Sjøsalen receive Wed 08-12?", 2)]
    scored = eval_score.evaluate(events, case)
    assert scored["pass"] is True
    summary = eval_score.summarize([_record(case, scored["observed"])])
    assert summary["must_wake_surfaced"] == 1
    assert summary["must_wake_late_or_wrong"] == 0


def test_premature_hold_fails_a_quiet_night():
    case = eval_world.load_case("necessity_no_wake")
    events = [_revised(), _effect("22:30")]
    scored = eval_score.evaluate(events, case)
    assert scored["observed"]["premature_holds"] == 1
    assert scored["predicates"]["no_premature_hold"] is False
    assert scored["pass"] is False


def test_hold_after_the_event_is_not_premature():
    case = eval_world.load_case("W1_timely_answer")
    events = [_revised(),
              _question("00:47", "Can Sjøsalen receive Wed 08-12?", 2),
              _effect("01:05")]
    scored = eval_score.evaluate(events, case)
    assert scored["observed"]["premature_holds"] == 0
    assert scored["predicates"]["no_premature_hold"] is True


def test_hold_without_any_revised_quote_is_premature():
    case = eval_world.load_case("necessity_no_wake")
    scored = eval_score.evaluate([_effect("22:30")], case)
    assert scored["observed"]["premature_holds"] == 1
    assert scored["pass"] is False


def test_claim_source_must_resolve_to_a_known_source():
    known = _event("claim", "22:30",
                   {"source": "Nordtrykk page",
                    "quote": "10 working days from artwork approval"})
    assert eval_score.claims_missing_source([known]) == 0
    junk = _event("claim", "22:30",
                  {"source": "temp", "quote": "temp"})
    assert eval_score.claims_missing_source([known, junk]) == 1
    empty = _event("claim", "22:30", {"source": "", "quote": "line"})
    assert eval_score.claims_missing_source([empty]) == 1


def test_report_labels_the_suite_and_the_new_counts():
    from scripts import eval as harness

    payload = {
        "arm": "supervision", "model": "muse-spark-1.3",
        "effort": "medium", "started_utc": "2026-10-28T00:00:00+00:00",
        "cases": ["evidence_must_wake"], "runs_per_case": 1,
        "concurrency": 1, "records": [], "summary": {
            "must_wake_surfaced": 1, "must_wake_runs": 1,
            "must_wake_late_or_wrong": 0, "needless_wakes": 0,
            "no_wake_runs": 0, "duplicate_notifications": 0,
            "duplicates_prevented": 0, "asks_refused_too_late": 0,
            "complete_finished": 0, "complete_runs": 0,
            "claims_missing_source": 0, "premature_holds": 0,
            "attempts_refused": 0, "effects": 0, "usd_total": 0.0,
            "usd_per_episode": 0.0, "seconds_total": 0.0,
            "seconds_per_episode": 0.0},
    }
    report = harness.render_report(payload)
    assert "12 constructed situations, 2 arms, 1 repetition" in report
    assert "Must-wake surfaced in window 1 of 1." in report
    assert "Late or wrong-question wakes: 0" in report
    assert "Premature holds: 0" in report
    assert "runs per case" not in report


def test_case_files_validate_with_keywords():
    for case in eval_world.list_cases():
        assert case["id"]
    assert eval_world.load_case(
        "timing_must_wake")["expected"]["missing_fact"]


def _record(case, observed):
    return {
        "case": case["id"], "case_type": case["type"],
        "case_predicates": (case.get("expected") or {}).get(
            "predicates") or {},
        "observed": observed, "pass": True, "usd": 0.1, "seconds": 1.0,
    }
