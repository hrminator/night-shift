"""Print a compact honest summary of a job export for the build log."""

from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, ".")

KINDS = ("decision", "question", "check", "effect", "step_failed",
         "nudge", "model_plain_text", "tool_limit", "claim",
         "owner_answer")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else max(
        glob.glob("data/runs/job-*.json"), key=os.path.getmtime)
    record = json.load(open(path, encoding="utf-8"))
    events = record["events"]
    print(f"file: {path}  events: {len(events)}")
    for event in events:
        if event["kind"] in KINDS:
            text = str(event["payload"])[:280].replace("\n", " ")
            print(f"{event['id']} {event['kind']} {event['virtual_time']} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
