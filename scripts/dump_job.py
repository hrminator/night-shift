"""Dump full decision/question payloads and usage keys for one job."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from app.adapter import log_path_for
from app.store import list_events

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "ec6c95529667"

for event in list_events(JOB_ID):
    if event["kind"] in ("decision", "question"):
        print(f"== {event['kind']} {event['id']} ==")
        print(json.dumps(event["payload"], ensure_ascii=False, indent=2))

path = log_path_for()
lines = path.read_text(encoding="utf-8").splitlines()
print("== last 4 response usage keys ==")
for line in lines[-4:]:
    record = json.loads(line)
    usage = record["response"].get("usage", {}) or {}
    print(json.dumps(
        {"effort": record.get("effort"), "status": record["response"].get("status"),
         "usage": usage}, ensure_ascii=False))
