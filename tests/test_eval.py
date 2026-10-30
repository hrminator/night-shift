"""Evaluation harness and scorer (pure code, stub model nights)."""

from __future__ import annotations

import json

from app import eval_night, eval_score, eval_world, runner
from app.store import append_event, create_job, list_events

VENUE_ADDRESS = "Sjøsalen, Sjøgaten 5, 5003 Bergen (fictional)"
CONTACT = ("Kari Strandli, studio coordinator,"
           " orders@fjord-fern.example.com, +47 22 00 11 22")


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _text(words):
    return {"type": "message", "content": [
        {"type": "output_text", "text": words}]}


def _ask_args():
    return {
        "question": "Can the venue receive Wed 08-12?",
        "why_now": "cutoff near", "what_checked": "sources",
        "if_yes": "hold", "if_no": "no hold",
        "options": ["Bergen: the venue can receive it", "No / not sure"],
    }


def _hold_args(answer_id):
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
                                      "id": answer_id},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"},
        },
    }


def _claim_calls(prefix, count=3):
    return [_call("record_claim",
                  {"source": f"doc-{prefix}-{i}",
                   "quote": f"line {i}"}, f"{prefix}-claim-{i}")
            for i in range(count)]


def _check_calls(prefix):
    return [_call("run_check",
                  {"name": name, "result": "fail", "evidence": [],
                   "note": "stub"}, f"{prefix}-check-{name}")
            for name in runner.CHECK_NAMES]


def _stub_night(job_ref):
    """One respond function for read, reassess and resume turns."""
    read = [
        {"output": _claim_calls("read", 3), "text": ""},
        {"output": [
            _call("record_decision",
                  {"outcome": "no_wake", "reason": "stub", "evidence": []},
                  "read-dec"),
            _call("propose_message",
                  {"to": "o", "subject": "s", "body": "comparison",
                   "purpose": "comparison"}, "read-d1"),
            _call("propose_message",
                  {"to": "o", "subject": "s", "body": "rannavere",
                   "purpose": "rannavere order"}, "read-d2"),
        ], "text": ""},
        {"output": [_text("read done")], "text": "read done"},
    ]
    reassess = [
        {"output": _claim_calls("re", 1) + _check_calls("re") + [
            _call("record_decision",
                  {"outcome": "wake", "reason": "stub", "evidence": []},
                  "re-dec"),
            _call("ask_owner", _ask_args(), "re-ask"),
        ], "text": ""},
        {"output": [_text("reassess done")], "text": "reassess done"},
    ]
    resume = {"n": 0}

    def respond(instructions, input_items, **kwargs):
        if "It is 21:35" in instructions:
            return read.pop(0)
        if "re-assessing" in instructions:
            return reassess.pop(0)
        if "has answered" in instructions:
            resume["n"] += 1
            from app.store import list_jobs
            only_job = list_jobs()[0]["id"]
            answer = [e for e in list_events(only_job)
                      if e["kind"] == "owner_answer"][-1]
            args = _hold_args(answer["id"])
            if resume["n"] == 1:
                return {"output": [
                    _call("submit_hold", args, "res-hold"),
                    _call("propose_message",
                          {"to": "o", "subject": "s", "body": "order",
                           "purpose": "order"}, "res-d1"),
                    _call("propose_message",
                          {"to": "o", "subject": "s", "body": "venue",
                           "purpose": "venue_note"}, "res-d2"),
                    _call("propose_message",
                          {"to": "o", "subject": "s", "body": "rannavere",
                           "purpose": "baltic_note"}, "res-d3"),
                ], "text": ""}
            if resume["n"] == 2:
                return {"output": [_call("submit_hold", args,
                                         "res-hold-retry")], "text": ""}
            return {"output": [_text("resume done")], "text": "resume done"}
        raise AssertionError(instructions[:80])

    return respond


def _run_stub(case_id, arm, tmp_path):
    case = eval_world.load_case(case_id)
    respond = _stub_night({})
    data_dir = tmp_path / "data"
    result = eval_night.run_case(
        case, arm, respond, data_dir, tmp_path / "work",
        tmp_path / "job.json",
        upload_fn=lambda path: {"id": "file-stub"},
        delete_fn=lambda fid: None)
    return case, result, data_dir / "night_shift.db"


def test_stub_decision_only_night_scores(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    case, result, db = _run_stub("evidence_must_wake", "supervision",
                                 tmp_path)
    assert result["status"] == "waiting_for_owner"
    events = list_events(result["job_id"], path=db)
    scored = eval_score.evaluate(events, case)
    assert scored["observed"]["notified"] is True
    assert scored["pass"] is True
    other = eval_world.load_case("evidence_no_wake")
    assert eval_score.evaluate(events, other)["pass"] is False


def test_stub_complete_night_places_one_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    case, result, db = _run_stub("W1_timely_answer", "supervision", tmp_path)
    assert result["status"] == "done"
    events = list_events(result["job_id"], path=db)
    scored = eval_score.evaluate(events, case)
    assert scored["observed"]["holds"] == 1
    assert scored["pass"] is True


def test_stub_portal_retry_leaves_exactly_one_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    case, result, db = _run_stub("W4_portal_error", "supervision", tmp_path)
    assert result["status"] == "done"
    events = list_events(result["job_id"], path=db)
    scored = eval_score.evaluate(events, case)
    assert scored["observed"]["holds"] == 1
    assert scored["observed"]["portal_errors"] >= 1
    assert scored["pass"] is True


def test_gateway_portal_error_is_retryable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import gateway, portal
    job = create_job(status="running", current_step="resuming",
                     virtual_time="01:05")
    job_id = job["id"]
    append_event(job_id, "21:30", "handoff",
                 {"brief": "fixtures/brief.md", "source": "owner"})
    append_event(job_id, "00:47", "question",
                 {"question": "Can the venue receive Wed 08-12?",
                  "why_now": "cutoff near", "what_checked": "sources",
                  "if_yes": "hold", "if_no": "no hold",
                  "options": ["yes", "No / not sure"]})
    answer = append_event(job_id, "01:05", "owner_answer",
                          {"choice": "yes", "source": "owner"})
    args = _hold_args(answer["id"])
    original = portal.ensure_hold
    state = {"failed": False}

    def flaky(*call_args, **call_kwargs):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("simulated portal outage")
        return original(*call_args, **call_kwargs)

    portal.ensure_hold = flaky  # type: ignore[method-assign]
    try:
        first = gateway.check_submit_hold(job_id, args, "01:05")
        assert first["ok"] is False
        assert first.get("retryable") is True
        second = gateway.check_submit_hold(job_id, args, "01:05")
        assert second["ok"] is True
    finally:
        portal.ensure_hold = original  # type: ignore[method-assign]
    effects = [e for e in list_events(job_id) if e["kind"] == "effect"]
    assert len(effects) == 1
    assert "portal_error" in [e["kind"] for e in list_events(job_id)]


def test_summarize_keeps_arms_and_types_separate():
    def record(case_type, notified_want, notified, complete_pass):
        return {
            "case_type": case_type,
            "case_predicates": {"notified": notified_want},
            "observed": {"notified": notified,
                         "notified_at": "00:47" if notified else None,
                         "notifications": 1 if notified else 0,
                         "claims_missing_source": 0,
                         "attempts_refused": 0, "effects": 0},
            "pass": complete_pass, "usd": 0.5, "seconds": 10.0,
        }
    records = [record("decision_only", True, True, True),
               record("decision_only", False, True, True),
               record("complete_job", True, True, True),
               record("complete_job", True, True, False)]
    summary = eval_score.summarize(records)
    assert (summary["must_wake_surfaced"], summary["must_wake_runs"]) == (1, 1)
    assert (summary["needless_wakes"], summary["no_wake_runs"]) == (1, 1)
    assert (summary["complete_finished"], summary["complete_runs"]) == (1, 2)
    assert "merged" not in " ".join(summary).lower()


def test_parse_args_concurrency_defaults_and_validates():
    from scripts import eval as harness
    assert harness.parse_args(["--arm", "direct"]).concurrency == 2
    assert harness.parse_args(
        ["--arm", "direct", "--concurrency", "1"]).concurrency == 1
    for bad in ("0", "-2"):
        try:
            harness.parse_args(["--arm", "direct", "--concurrency", bad])
        except SystemExit:
            pass
        else:  # noqa: E701 - must not accept bad concurrency
            raise AssertionError(bad)


def _stub_record(episode, case_id, notified):
    return {
        "episode": episode, "case": case_id, "run": 1,
        "status": "waiting_for_owner", "pass": True,
        "usd": 0.1, "seconds": 1.0, "wall_seconds": 0.1,
        "case_type": "decision_only",
        "case_predicates": {"notified": notified},
        "observed": {"notified": notified, "notified_at": "00:47",
                     "notifications": 1, "claims_missing_source": 0,
                     "attempts_refused": 0, "effects": 0,
                     "duplicates_prevented": 0,
                     "asks_refused_too_late": 0},
        "decision_reason": "Stub reason for ordering.",
    }


def _stub_cases():
    return [
        {"id": "b-case", "type": "decision_only",
         "expected": {"predicates": {"notified": True}}},
        {"id": "a-case", "type": "decision_only",
         "expected": {"predicates": {"notified": False}}},
    ]


def test_run_all_parallel_keeps_episode_order(tmp_path, monkeypatch):
    import time as _time

    from scripts import eval as harness

    def fake_run_once(arm, case, run, out_dir, episode):
        if episode == 1:
            _time.sleep(0.2)
        return _stub_record(episode, case["id"], True)

    monkeypatch.setattr(harness, "run_once", fake_run_once)
    payload = harness.run_all("supervision", _stub_cases(), 1,
                              tmp_path / "out", concurrency=2)
    assert [record["episode"] for record in payload["records"]] == [1, 2]
    assert payload["concurrency"] == 2
    assert (tmp_path / "out" / "results.json").exists()
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "Stub reason for ordering." in report
    assert "Duplicates prevented by the app" in report


def test_run_all_sequential_path(tmp_path, monkeypatch):
    from scripts import eval as harness

    seen = []

    def fake_run_once(arm, case, run, out_dir, episode):
        seen.append(episode)
        return _stub_record(episode, case["id"], False)

    monkeypatch.setattr(harness, "run_once", fake_run_once)
    payload = harness.run_all("direct", _stub_cases(), 1,
                              tmp_path / "out", concurrency=1)
    assert seen == [1, 2]
    assert [record["episode"] for record in payload["records"]] == [1, 2]


def test_thread_data_dirs_are_isolated(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor as _Pool

    from app import store
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))

    def work(sub):
        store.set_thread_data_dir(tmp_path / sub)
        try:
            job = store.create_job()
            return (str(store.db_path()), job["id"],
                    [item["id"] for item in store.list_jobs()])
        finally:
            store.clear_thread_data_dir()

    with _Pool(max_workers=2) as pool:
        first, second = list(pool.map(work, ["one", "two"]))
    assert first[0] != second[0]
    assert first[1] != second[1]
    assert first[2] == [first[1]]
    assert second[2] == [second[1]]
    assert store.db_path().parent == tmp_path / "env"
