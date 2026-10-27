"""Inspect a night-job run: events plus the last response's item types."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.store import list_events


def main() -> int:
    job_id = sys.argv[1]
    events = list_events(job_id)
    print(f"events: {len(events)}")
    for event in events:
        payload = event["payload"] or {}
        keys = sorted(payload.keys())
        print(f"  seq={event['seq']} kind={event['kind']} "
              f"vt={event['virtual_time']} keys={keys}")
    log_dir = Path("logs")
    lines = sorted(log_dir.glob("responses-*.jsonl"))
    print(f"log files: {[p.name for p in lines]}")
    if lines:
        last = lines[-1].read_text(encoding="utf-8").strip().split("\n")[-1]
        record = json.loads(last)
        output = (record.get("response") or {}).get("output") or []
        kinds = [f"{i.get('type')}:{i.get('name', '')}" for i in output]
        print(f"last response items: {kinds}")
        for item in output:
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        print("TEXT:" + part.get("text", "")[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
