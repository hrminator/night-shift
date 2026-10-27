"""Print the full decision payload of a job."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from app.store import list_events


def main() -> int:
    job_id = sys.argv[1]
    for event in list_events(job_id):
        if event["kind"] in ("decision", "question"):
            print(json.dumps(event["payload"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
