"""Thin client for the Meta Model API Responses endpoint.

Every call sends ``store:false`` and ``include:["reasoning.encrypted_content"]``,
resends instructions, tools and reasoning effort each time, never uses
``previous_response_id``, and always sets ``max_output_tokens``.

The full request body and response body (never the Authorization header) are
appended as one JSON line to ``logs/responses-<UTC date>.jsonl``, including the
``model`` field the response reports.

Returned output items are kept in order -- including encrypted ``reasoning``
items -- so they can be sent back as ``input`` on the next call (stateless
encrypted-reasoning replay; see AGENTS.md non-negotiable 8).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://api.meta.ai/v1"
RESPONSES_PATH = "/responses"
MODEL = "muse-spark-1.3"
KEY_ENV_VAR = "NIGHT_SHIFT_API_KEY_EVAL"

INCLUDE_ENCRYPTED_REASONING = ["reasoning.encrypted_content"]

DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_TIMEOUT_SECONDS = 120.0


def log_path_for(now: datetime | None = None) -> Path:
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    return Path("logs") / f"responses-{day}.jsonl"


def api_key() -> str:
    """Read the eval key from the environment. Never logged or printed."""
    import os

    key = os.environ.get(KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{KEY_ENV_VAR} is not set in the environment; "
            "export it before making model calls."
        )
    return key


def build_request(
    instructions: str,
    input_items: list | str,
    tools: list | None = None,
    effort: str = "low",
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict:
    """Build a stateless Responses request body.

    ``input_items`` is either a plain user-message string or a list of input
    items (for replay: the previous turn's output items in order, followed by
    the new items). ``previous_response_id`` is never used.
    """
    body = {
        "model": MODEL,
        "instructions": instructions,
        "input": input_items,
        "tools": list(tools) if tools else [],
        "tool_choice": "auto",
        "reasoning": {"effort": effort},
        "store": False,
        "include": list(INCLUDE_ENCRYPTED_REASONING),
        "max_output_tokens": max_output_tokens,
    }
    assert "previous_response_id" not in body
    return body


def reasoning_items_of(output_items: list) -> list:
    return [item for item in output_items if item.get("type") == "reasoning"]


def drop_reasoning_items(items: list) -> list:
    """Remove reasoning items whole (fallback when a replay gets HTTP 400)."""
    return [item for item in items if item.get("type") != "reasoning"]


def output_text_of(output_items: list) -> str:
    chunks: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                chunks.append(part.get("text", ""))
    return "".join(chunks)


def _append_log(record: dict, path: Path | None = None) -> Path:
    path = path or log_path_for()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _post(body: dict, timeout: float) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
    }
    url = BASE_URL + RESPONSES_PATH
    with httpx.Client(timeout=timeout) as client:
        return client.post(url, headers=headers, json=body)


def respond(
    instructions: str,
    input_items: list | str,
    tools: list | None = None,
    effort: str = "low",
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Make one Responses call and return the parsed result.

    Returns ``{"model": ..., "response_id": ..., "output": [...],
    "usage": {...}, "text": ...}``. On HTTP 400 with reasoning items in the
    replayed input, retries once with the reasoning items dropped whole and
    records that fallback in the log.
    """
    body = build_request(instructions, input_items, tools, effort, max_output_tokens)
    started = datetime.now(timezone.utc)
    response = _post(body, timeout)
    fallback = None
    if response.status_code == 400 and isinstance(input_items, list):
        dropped = drop_reasoning_items(input_items)
        if len(dropped) != len(input_items):
            fallback = {
                "dropped_reasoning_items": len(input_items) - len(dropped),
                "first_status": 400,
                "first_error": response.text[:2000],
            }
            body = build_request(
                instructions, dropped, tools, effort, max_output_tokens
            )
            response = _post(body, timeout)
    finished = datetime.now(timezone.utc)
    response.raise_for_status()
    payload = response.json()
    output_items = payload.get("output", [])
    result = {
        "model": payload.get("model"),
        "response_id": payload.get("id"),
        "output": output_items,
        "usage": payload.get("usage", {}),
        "text": output_text_of(output_items),
        "seconds": (finished - started).total_seconds(),
    }
    _append_log(
        {
            "ts": finished.isoformat(),
            "effort": effort,
            "request": body,
            "response": payload,
            "fallback": fallback,
        }
    )
    return result
