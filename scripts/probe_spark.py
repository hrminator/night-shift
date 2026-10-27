"""Day 1 probe: one real Spark call at each effort level.

Sends a short instruction plus one user message at effort minimal, low and
medium, and prints seconds, input/output/reasoning tokens and the model
field the response reports. Request/response bodies (minus the key) are
logged to logs/ by app.adapter. The key is read from NIGHT_SHIFT_API_KEY_EVAL
and never printed.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from app.adapter import reasoning_items_of, respond

INSTRUCTION = (
    "You are a probe for the Night Shift project. "
    "Answer in one short sentence. Do not call any tools."
)
USER_MESSAGE = "Reply with exactly: probe ok."


def main() -> int:
    summary = []
    for effort in ("minimal", "low", "medium"):
        result = respond(
            INSTRUCTION, USER_MESSAGE, tools=[], effort=effort, max_output_tokens=64
        )
        usage = result.get("usage") or {}
        line = {
            "effort": effort,
            "seconds": round(result["seconds"], 2),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": (usage.get("reasoning_tokens")
                                 or (usage.get("output_tokens_details") or {}).get("reasoning_tokens")),
            "model": result.get("model"),
            "reasoning_items": len(reasoning_items_of(result["output"])),
            "text": result["text"][:200],
        }
        summary.append(line)
        print(json.dumps(line, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
