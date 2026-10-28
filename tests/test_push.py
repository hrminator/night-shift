"""Web Push notify tests (pure code): fake sender, no network.

The M14 notify step pushes once per live subscription for the operator's
own job only. Visitor copies and eval runs never push, a 410 marks the
subscription dead, disabled push is skipped, and the simulated question
event is unchanged so scoring is untouched.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.main as main_mod
import app.push as push_mod
from app import eval_night, eval_score, eval_world, replay, runner
from app.store import (append_event, create_job, get_job, list_events,
                       list_live_push_subscriptions, save_push_subscription)

QUESTION = {
    "question": "Can the venue receive Wed 08-12?",
    "why_now": "cutoff near",
    "what_checked": "sources",
    "if_yes": "hold",
    "if_no": "no hold",
    "options": ["Bergen: the venue can receive it", "No / not sure"],
}


def _enable_push(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "1")
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private")


def _fake_sender(calls, status_code=201):
    def fake(subscription, payload):
        calls.append((subscription, payload))
        return {"status_code": status_code}

    return fake


def _seed_question(job_id, question_text=None):
    payload = dict(QUESTION)
    if question_text is not None:
        payload["question"] = question_text
    return append_event(job_id, "00:47", "question", payload)


def test_push_skipped_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUSH_ENABLED", raising=False)
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone")
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"])
    runner.save_checkpoint(job["id"], [], asked["id"])
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert kinds == ["question", "checkpoint", "push_skipped"]
    assert list_events(job["id"])[-1]["payload"] == {"reason": "disabled"}
    assert calls == []


def test_push_skipped_when_keys_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUSH_ENABLED", "1")
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone")
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"])
    runner.save_checkpoint(job["id"], [], asked["id"])
    events = list_events(job["id"])
    assert [e["kind"] for e in events] == [
        "question", "checkpoint", "push_skipped"]
    assert events[-1]["payload"] == {"reason": "disabled"}
    assert calls == []


def test_owner_job_pushes_once_per_live_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    live = save_push_subscription("https://push.example.invalid/1",
                                  {"p256dh": "k", "auth": "a"}, "phone")
    dead = save_push_subscription("https://push.example.invalid/2",
                                  {"p256dh": "k", "auth": "a"}, "old phone")
    from app.store import mark_push_subscription_dead
    mark_push_subscription_dead(dead["id"])
    assert [s["id"] for s in list_live_push_subscriptions()] == [live["id"]]
    long_text = "Can the venue receive the bags on Wednesday morning? " + \
        "x" * 200
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"], question_text=long_text)
    runner.save_checkpoint(job["id"], [], asked["id"])
    assert len(calls) == 1
    subscription, payload = calls[0]
    assert subscription["endpoint"] == "https://push.example.invalid/1"
    assert payload["title"] == "Night Shift"
    assert payload["body"] == long_text[:120]
    assert len(payload["body"]) == 120
    assert payload["url"] == f"/jobs/{job['id']}"
    sent = [e for e in list_events(job["id"]) if e["kind"] == "push_sent"]
    assert len(sent) == 1
    assert sent[0]["payload"]["subscription_id"] == live["id"]
    assert sent[0]["payload"]["status_code"] == 201
    assert isinstance(sent[0]["payload"]["seconds"], float)
    assert get_job(job["id"])["status"] == "waiting_for_owner"


def test_push_failure_never_fails_the_night(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)

    def boom(subscription, payload):
        raise push_mod.PushError("push service down")

    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", boom)
    sub = save_push_subscription("https://push.example.invalid/1",
                                 {"p256dh": "k", "auth": "a"}, "phone")
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"])
    runner.save_checkpoint(job["id"], [], asked["id"])
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert kinds == ["question", "checkpoint", "push_failed"]
    failed = list_events(job["id"])[-1]
    assert failed["payload"]["subscription_id"] == sub["id"]
    assert "down" in failed["payload"]["error"]
    assert get_job(job["id"])["status"] == "waiting_for_owner"


def test_gone_subscription_is_marked_dead(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)
    calls = []

    def gone(subscription, payload):
        calls.append((subscription, payload))
        raise push_mod.PushError("subscription gone", status=410)

    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", gone)
    sub = save_push_subscription("https://push.example.invalid/1",
                                 {"p256dh": "k", "auth": "a"}, "phone")
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"])
    runner.save_checkpoint(job["id"], [], asked["id"])
    assert len(calls) == 1
    assert list_live_push_subscriptions() == []
    push_mod.notify_owner_job(job["id"], asked["id"], "00:47")
    assert len(calls) == 1
    kinds = [e["kind"] for e in list_events(job["id"])]
    assert kinds == ["question", "checkpoint", "push_failed", "push_skipped"]
    assert list_events(job["id"])[-1]["payload"] == {
        "reason": "no_subscriptions"}


def test_question_event_unchanged_and_scoring_untouched(tmp_path,
                                                        monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone")
    job = create_job(status="running", owner_job=True, virtual_time="00:39")
    asked = _seed_question(job["id"])
    before = json.loads(json.dumps(asked))
    runner.save_checkpoint(job["id"], [], asked["id"])
    after = next(e for e in list_events(job["id"])
                 if e["kind"] == "question")
    assert after == before
    seen = eval_score.observed(list_events(job["id"]))
    assert seen["notified"] is True
    assert seen["notifications"] == 1
    assert seen["notified_at"] == "00:47"


def test_visitor_copy_never_pushes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone")
    record = {"job_id": "rec-push-1", "events": [
        {"id": 1, "virtual_time": "21:30", "kind": "handoff",
         "payload": {"source": "owner", "variant": "hero"}},
        {"id": 2, "virtual_time": "00:47", "kind": "question",
         "payload": dict(QUESTION)},
        {"id": 3, "virtual_time": "00:47", "kind": "checkpoint",
         "payload": {"question_event_id": 2, "next_input": []}},
    ]}
    new_id = replay.copy_job_for_visitor(
        record, "Bergen: the venue can receive it")
    assert get_job(new_id)["owner_job"] == 0
    kinds = [e["kind"] for e in list_events(new_id)]
    assert kinds == ["handoff", "question", "checkpoint",
                       "permission_parsed", "provenance", "owner_answer"]
    assert calls == []


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def _text(words):
    return {"type": "message", "content": [
        {"type": "output_text", "text": words}]}


def _eval_respond():
    read = [
        {"output": [_call("record_claim", {"source": "doc", "quote": "line"},
                          "c1")], "text": ""},
        {"output": [_call("record_decision",
                          {"outcome": "no_wake", "reason": "stub",
                           "evidence": []}, "d1")], "text": ""},
        {"output": [_text("read done")], "text": "read done"},
    ]
    reassess = [
        {"output": [
            _call("record_claim", {"source": "Q-1187-B", "quote": "dispatch"},
                  "c2"),
            *[_call("run_check",
                    {"name": name, "result": "fail", "evidence": [],
                     "note": "stub"}, f"k-{name}")
              for name in runner.CHECK_NAMES],
            _call("record_decision", {"outcome": "wake", "reason": "stub",
                                      "evidence": []}, "d2"),
            _call("ask_owner", dict(QUESTION), "a1"),
        ], "text": ""},
        {"output": [_text("reassess done")], "text": "reassess done"},
    ]

    def respond(instructions, input_items, **kwargs):
        if "It is 21:35" in instructions:
            return read.pop(0)
        if "re-assessing" in instructions:
            return reassess.pop(0)
        raise AssertionError(instructions[:80])

    return respond


def test_eval_run_never_pushes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env"))
    _enable_push(monkeypatch)
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone",
                           path=data_dir / "night_shift.db")
    case = eval_world.load_case("evidence_must_wake")
    result = eval_night.run_case(
        case, "supervision", _eval_respond(), data_dir, tmp_path / "work",
        tmp_path / "job.json",
        upload_fn=lambda path: {"id": "file-stub"},
        delete_fn=lambda fid: None)
    assert result["status"] == "waiting_for_owner"
    db = data_dir / "night_shift.db"
    assert get_job(result["job_id"], path=db)["owner_job"] == 0
    kinds = [e["kind"] for e in list_events(result["job_id"], path=db)]
    assert "question" in kinds and "checkpoint" in kinds
    assert not [kind for kind in kinds if kind.startswith("push_")]
    assert calls == []


def test_jobs_run_marks_owner_job(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TOKEN", "test-token")
    captured = {}

    def fake_run_job(variant="hero", owner_job=False):
        captured["owner_job"] = owner_job
        return {"job_id": "abc", "status": "done"}

    monkeypatch.setattr("app.runner.run_job", fake_run_job)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post("/jobs/run",
                           headers={"X-Run-Token": "test-token"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert captured == {"owner_job": True}


def test_subscribe_needs_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RUN_TOKEN", "test-token")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = {"endpoint": "https://push.example.invalid/1",
            "keys": {"p256dh": "k", "auth": "a"}}
    assert client.post("/owner/phone/subscribe",
                       json=body).status_code == 403
    assert client.post("/owner/phone/subscribe?token=wrong",
                       json=body).status_code == 403
    assert client.get("/owner/phone").status_code == 403
    response = client.post("/owner/phone/subscribe",
                           headers={"X-Run-Token": "test-token"}, json=body)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    page = client.get("/owner/phone?token=test-token")
    assert page.status_code == 200
    assert "This phone is subscribed as the owner's phone" in page.text
    assert "Send test push" in page.text
    assert "test-token" not in page.text


def test_morning_page_push_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _enable_push(monkeypatch)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    save_push_subscription("https://push.example.invalid/1",
                           {"p256dh": "k", "auth": "a"}, "phone")
    calls = []
    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", _fake_sender(calls))
    owner = create_job(status="running", owner_job=True,
                       virtual_time="00:39")
    asked = _seed_question(owner["id"])
    runner.save_checkpoint(owner["id"], [], asked["id"])
    body = client.get(f"/jobs/{owner['id']}/morning").text
    assert "Notification" in body
    assert "Delivered by web push to the owner" in body

    def boom(subscription, payload):
        raise push_mod.PushError("push service down")

    monkeypatch.setattr(push_mod, "SEND_PUSH_FN", boom)
    failing = create_job(status="running", owner_job=True,
                         virtual_time="00:39")
    asked_failing = _seed_question(failing["id"])
    runner.save_checkpoint(failing["id"], [], asked_failing["id"])
    failing_body = client.get(f"/jobs/{failing['id']}/morning").text
    assert "Web push failed" in failing_body

    visitor = create_job(status="running", virtual_time="00:39")
    asked_visitor = _seed_question(visitor["id"])
    runner.save_checkpoint(visitor["id"], [], asked_visitor["id"])
    visitor_body = client.get(f"/jobs/{visitor['id']}/morning").text
    assert "Delivered by web push" not in visitor_body
    assert "Web push failed" not in visitor_body
