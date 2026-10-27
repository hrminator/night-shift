"""Run one real decision turn and print an honest summary for the build log.

Usage: uv run python scripts/run_job_once.py
Prints job id, claims, decision, question, and seconds/tokens per call
(taken from the response log lines this run appended).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.adapter import log_path_for
from app.runner import export_job, run_job
from app.store import list_events


def main() -> None:
    started = datetime.now(timezone.utc)
    log_path = log_path_for()
    before = 0
    if log_path.exists():
        before = len(log_path.read_text(encoding="utf-8").splitlines())
    summary = run_job()
    job_id = summary["job_id"]
    print("job_id:", job_id)
    print("status:", summary["status"])
    events = list_events(job_id)
    for event in events:
        payload = event["payload"] or {}
        if event["kind"] == "claim":
            print(f"- claim {event['id']}: {payload.get('source')}: "
                  f"{payload.get('quote', '')[:100]}")
        elif event["kind"] == "decision":
            print(f"- decision {event['id']}: {payload.get('outcome')}: "
                  f"{str(payload.get('reason', ''))[:300]}")
            print(f"  evidence: {payload.get('evidence')}")
        elif event["kind"] == "question":
            print(f"- question {event['id']}: {payload.get('question', '')[:300]}")
            print(f"  options: {payload.get('options')}")
        elif event["kind"] in ("step_failed", "model_plain_text", "tool_limit"):
            print(f"- {event['kind']}: {json.dumps(payload)[:200]}")
    lines = log_path.read_text(encoding="utf-8").splitlines()[before:]
    prev_ts = started
    for line in lines:
        record = json.loads(line)
        usage = record["response"].get("usage", {}) or {}
        ts = datetime.fromisoformat(record["ts"])
        print(f"- call effort={record.get('effort')} "
              f"seconds={(ts - prev_ts).total_seconds():.1f} "
              f"model={record['response'].get('model')} "
              f"status={record['response'].get('status')} "
              f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
              f"reasoning={usage.get('reasoning_tokens')}")
        prev_ts = ts
    out = export_job(job_id)
    print("exported:", out)


if __name__ == "__main__":
    main()
