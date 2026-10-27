"""Drive the whole ugly loop for real through the HTTP routes.

POST /jobs/run -> read question -> POST answer at 01:05 -> POST resume ->
check exactly one hold effect -> GET morning page. Uses the live database
(DATA_DIR=data). Prints what Spark did on resume and per-call usage.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

import app.main as main_mod
from app.adapter import log_path_for
from app.runner import export_job
from app.store import list_events

ANSWER = "Bergen: the venue can receive it"


def log_lines_since(position: int) -> list[dict]:
    path = log_path_for()
    lines = path.read_text(encoding="utf-8").splitlines()[position:]
    return [json.loads(line) for line in lines]


def print_calls(records: list[dict], since: datetime, label: str) -> None:
    prev = since
    print(f"== {label}: {len(records)} model calls ==")
    for record in records:
        usage = record["response"].get("usage", {}) or {}
        details = usage.get("output_tokens_details", {}) or {}
        ts = datetime.fromisoformat(record["ts"])
        print(f"- effort={record.get('effort')} "
              f"seconds={(ts - prev).total_seconds():.1f} "
              f"model={record['response'].get('model')} "
              f"status={record['response'].get('status')} "
              f"in={usage.get('input_tokens')} "
              f"out={usage.get('output_tokens')} "
              f"reasoning={details.get('reasoning_tokens')}")
        prev = ts


def main() -> None:
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    position = len(
        log_path_for().read_text(encoding="utf-8").splitlines()
        if log_path_for().exists() else [])
    started = datetime.now(timezone.utc)

    response = client.post("/jobs/run", follow_redirects=False)
    assert response.status_code == 303, response.status_code
    job_id = response.headers["location"].rsplit("/", 1)[-1]
    print("job_id:", job_id)
    print_calls(log_lines_since(position), started, "decision turn")
    position += len(log_lines_since(position))

    events = list_events(job_id)
    questions = [e for e in events if e["kind"] == "question"]
    assert questions, "no question asked"
    question = questions[-1]["payload"] or {}
    print("question:", question.get("question"))
    print("options:", question.get("options"))

    resumed_at = datetime.now(timezone.utc)
    response = client.post(
        f"/jobs/{job_id}/answer",
        content=urllib.parse.urlencode({"choice": ANSWER}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.status_code

    response = client.post(f"/jobs/{job_id}/resume", follow_redirects=False)
    assert response.status_code == 303, (response.status_code,
                                        response.text[:300])
    print_calls(log_lines_since(position), resumed_at, "resume turn")

    events = list_events(job_id)
    effects = [e for e in events if e["kind"] == "effect"]
    assert len(effects) == 1, f"expected 1 hold, got {len(effects)}"
    print("acknowledgement:",
          effects[0]["payload"].get("acknowledgement"))
    tools = [(e["kind"], (e["payload"] or {}).get("tool"),
              (e["payload"] or {}).get("ok"),
              (e["payload"] or {}).get("reason", "")) for e in events
             if e["kind"] in ("gateway_result", "attempt_refused",
                              "tool_malformed")]
    print("gateway/tool records:", json.dumps(tools, ensure_ascii=False))
    drafts = [e for e in events if e["kind"] == "draft"]
    print(f"drafts: {len(drafts)}")
    for draft in drafts:
        payload = draft["payload"] or {}
        print(f"- to={payload.get('to')} subject={payload.get('subject')} "
              f"purpose={payload.get('purpose')} "
              f"status={payload.get('status')}")
        print(f"  body: {str(payload.get('body', ''))[:220]}")

    response = client.get(f"/jobs/{job_id}/morning")
    assert response.status_code == 200, response.status_code
    for needle in ("Vestland slot held until 09:00", "H-2041",
                   "Simulated supplier system", "Approve this exact text"):
        assert needle in response.text, needle
    print("morning page: label, acknowledgement, drafts, approve buttons OK")
    out = export_job(job_id)
    print("exported:", out)


if __name__ == "__main__":
    main()
