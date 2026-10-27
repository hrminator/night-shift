"""Day 2 step A: run one real night job against Spark and export its log.

Run: uv run python scripts/run_night.py
Key: NIGHT_SHIFT_API_KEY_EVAL (never printed). Bodies logged by app.adapter.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from app import runner
from app.store import list_events


def main() -> int:
    summary = runner.run_job()
    job_id = summary["job_id"]
    out_path = runner.export_job(job_id)
    print(f"job: {job_id} status={summary['status']} export={out_path}")

    result = summary.get("result") or {}
    usage = result.get("usage") or {}
    print(json.dumps({
        "seconds": round(result.get("seconds", 0), 2),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": (
            usage.get("reasoning_tokens")
            or (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
        ),
        "model": result.get("model"),
        "status": result.get("status"),
    }))

    for event in list_events(job_id):
        kind = event["kind"]
        payload = event["payload"] or {}
        if kind == "claim":
            print(f"claim {event['id']}: {payload.get('source')!r} -> "
                  f"{str(payload.get('quote'))[:120]!r}")
        elif kind == "decision":
            print(f"decision {event['id']}: {payload.get('outcome')!r} "
                  f"reason={str(payload.get('reason'))[:300]!r}")
        elif kind == "question":
            print(f"QUESTION {event['id']}: {payload.get('question')!r}")
            print(f"  options: {payload.get('options')!r}")
        elif kind in ("tool_refused", "tool_malformed", "tool_limit",
                      "model_plain_text", "step_failed", "checkpoint"):
            print(f"{kind} {event['id']}: "
                  f"{json.dumps(payload)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
