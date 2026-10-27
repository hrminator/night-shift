"""Day 3 step C: replay the Day-1 encrypted reasoning items with a follow-up.

Loads logs/reasoning-2026-10-27.json (saved on Day 1), sends the reasoning
items back as input with a short follow-up question, and reports whether
the API accepted them (status, seconds) or returned HTTP 400. On a 400 the
adapter's drop-and-resume fallback (reasoning items dropped whole, resume
from messages and tool results) becomes the live path, and the fallback is
already logged in the responses log by app.adapter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.adapter import log_path_for, respond

REASONING_PATH = Path("logs/reasoning-2026-10-27.json")
INSTRUCTIONS = (
    "You are Night Shift, the overnight manager for one job: 100 tote bags "
    "for a Bergen customer day. This is a replay check: the first input "
    "items are your own earlier encrypted reasoning, sent back intact. "
    "Answer the follow-up in one short sentence."
)
FOLLOW_UP = "Follow-up: in one short sentence, what did the earlier probe reply?"


def main() -> int:
    saved = json.loads(REASONING_PATH.read_text(encoding="utf-8"))
    items = list(saved.get("items") or [])
    print(f"loaded {len(items)} reasoning items "
          f"(effort {saved.get('effort')}, model {saved.get('model')})")
    log_path = log_path_for()
    before = len(log_path.read_text(encoding="utf-8").splitlines()) \
        if log_path.exists() else 0
    replay_input = list(items) + [{
        "type": "message", "role": "user", "content": FOLLOW_UP,
    }]
    try:
        result = respond(INSTRUCTIONS, replay_input, tools=[],
                         effort="low", max_output_tokens=512)
    except Exception as exc:  # noqa: BLE001 - the outcome is the report
        print(f"REPLAY REFUSED: {type(exc).__name__}: {str(exc)[:300]}")
        print("Outcome: the API did not accept the replay; "
              "drop-and-resume is the live path.")
        return 0
    lines = log_path.read_text(encoding="utf-8").splitlines()[before:]
    fallback = None
    for line in lines:
        record = json.loads(line)
        if record.get("fallback"):
            fallback = record["fallback"]
    usage = result.get("usage") or {}
    print(f"status={result.get('status')} seconds={result['seconds']:.1f} "
          f"model={result.get('model')} "
          f"text={result.get('text', '')[:120]!r}")
    if fallback:
        print(f"HTTP 400 on the first attempt "
              f"({fallback.get('first_error', '')[:160]!r}); "
              f"dropped {fallback.get('dropped_reasoning_items')} reasoning "
              "items whole and resumed from messages and tool results. "
              "Outcome: drop-and-resume is the live path (logged).")
    else:
        print("Outcome: the API accepted the encrypted reasoning items; "
              "intact replay is the live path.")
    print(f"input_tokens={usage.get('input_tokens')} "
          f"output_tokens={usage.get('output_tokens')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
