"""Thin client for the Meta Model API Responses endpoint.

Every call sends ``store:false`` and ``include:["reasoning.encrypted_content"]``,
resends instructions, tools and reasoning effort each time, never uses
``previous_response_id``, and always sets ``max_output_tokens``.

Prompt-cache routing: every request carries a stable ``prompt_cache_key``
(``nightshift-<instrhash>-<call_type>``, one key per call type, never per
job) plus a ``prompt_cache_retention`` hint of ``24h``. Cached input tokens
are reported in ``usage.input_tokens_details.cached_tokens`` and logged with
every call.

The full request body and response body (never the Authorization header) are
appended as one JSON line to ``logs/responses-<UTC date>.jsonl``, including the
``model`` field the response reports.

Returned output items are kept in order -- including encrypted ``reasoning``
items -- so they can be sent back as ``input`` on the next call (stateless
encrypted-reasoning replay; see AGENTS.md non-negotiable 8).

One call type also sends ``text.format`` with a JSON schema (the B1
object-grounding call); it is logged like every other call.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://api.meta.ai/v1"
RESPONSES_PATH = "/responses"
MODEL = "muse-spark-1.3"
LIVE_KEY_ENV_VAR = "NIGHT_SHIFT_API_KEY_LIVE"
EVAL_KEY_ENV_VAR = "NIGHT_SHIFT_API_KEY_EVAL"
KEY_ENV_VAR = EVAL_KEY_ENV_VAR

INCLUDE_ENCRYPTED_REASONING = ["reasoning.encrypted_content"]

#: Prompt-cache retention hint (a hint, not a guarantee, per Meta's docs).
PROMPT_CACHE_RETENTION = "24h"

DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_TIMEOUT_SECONDS = 120.0


def log_path_for(now: datetime | None = None) -> Path:
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    return Path("logs") / f"responses-{day}.jsonl"


def api_key() -> str:
    """Read the live key first, falling back to the eval key. Never logged or printed."""
    import os

    key = os.environ.get(LIVE_KEY_ENV_VAR) or os.environ.get(EVAL_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{LIVE_KEY_ENV_VAR} / {EVAL_KEY_ENV_VAR} is not set in the environment; "
            "export it before making model calls."
        )
    return key


def prompt_cache_key_for(instructions: str, call_type: str) -> str:
    """One stable cache key per call type, never per job or per request.

    ``instrhash`` is the first 12 hex characters of the SHA-256 of the
    instructions string, so identical instruction text shares a key while
    different instruction text (another arm, another brief) does not.
    """
    digest = hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:12]
    return f"nightshift-{digest}-{call_type}"


def build_request(
    instructions: str,
    input_items: list | str,
    tools: list | None = None,
    effort: str = "low",
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    call_type: str = "read",
    text_format: dict | None = None,
) -> dict:
    """Build a stateless Responses request body.

    ``input_items`` is either a plain user-message string or a list of input
    items (for replay: the previous turn's output items in order, followed by
    the new items). ``previous_response_id`` is never used. ``text_format``
    (a ``{"type": "json_schema", ...}`` dict) is sent as ``text.format``
    when given; ``store`` stays False either way.
    """
    body = {
        "model": MODEL,
        "instructions": instructions,
        "input": input_items,
        "tools": list(tools) if tools else [],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": {"effort": effort},
        "store": False,
        "include": list(INCLUDE_ENCRYPTED_REASONING),
        "max_output_tokens": max_output_tokens,
        "prompt_cache_key": prompt_cache_key_for(instructions, call_type),
        "prompt_cache_retention": PROMPT_CACHE_RETENTION,
    }
    if text_format is not None:
        body["text"] = {"format": text_format}
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
    call_type: str = "read",
    text_format: dict | None = None,
) -> dict:
    """Make one Responses call and return the parsed result.

    Returns ``{"model": ..., "response_id": ..., "output": [...],
    "usage": {...}, "cached_tokens": ..., "text": ...}``. On HTTP 400 with reasoning items in the
    replayed input, retries once with the reasoning items dropped whole and
    records that fallback in the log. If the API rejects a prompt-cache
    field by name, that field is dropped and the call retried once without
    it, recorded the same way.
    """
    dropped_cache_fields: list[str] = []

    def _build(body_input: list | str = input_items) -> dict:
        built = build_request(
            instructions, body_input, tools, effort, max_output_tokens,
            call_type, text_format,
        )
        for field in dropped_cache_fields:
            built.pop(field, None)
        return built

    body = _build()
    started = datetime.now(timezone.utc)
    response = _post(body, timeout)
    fallback = None
    if response.status_code == 400:
        error_text = response.text
        named = [
            field
            for field in ("prompt_cache_key", "prompt_cache_retention")
            if field in error_text
        ]
        if named:
            dropped_cache_fields.extend(named)
            fallback = {
                "dropped_request_fields": list(dropped_cache_fields),
                "first_status": 400,
                "first_error": error_text[:2000],
            }
            body = _build()
            response = _post(body, timeout)
    if response.status_code == 400 and isinstance(input_items, list):
        dropped = drop_reasoning_items(input_items)
        if len(dropped) != len(input_items):
            if fallback is None:
                fallback = {
                    "dropped_reasoning_items": len(input_items) - len(dropped),
                    "first_status": 400,
                    "first_error": response.text[:2000],
                }
            else:
                fallback["dropped_reasoning_items"] = len(input_items) - len(
                    dropped
                )
            body = _build(dropped)
            response = _post(body, timeout)
    finished = datetime.now(timezone.utc)
    try:
        response.raise_for_status()
    except Exception:
        _append_log(
            {
                "ts": finished.isoformat(),
                "effort": effort,
                "call_type": call_type,
                "prompt_cache_key": body.get("prompt_cache_key"),
                "cached_tokens": 0,
                "request": body,
                "response_error": {
                    "status": response.status_code,
                    "text": response.text[:2000],
                },
                "fallback": fallback,
            }
        )
        raise
    payload = response.json()
    output_items = payload.get("output", [])
    usage = payload.get("usage", {}) or {}
    cached = int(
        (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0
    )
    result = {
        "model": payload.get("model"),
        "response_id": payload.get("id"),
        "status": payload.get("status"),
        "incomplete_details": payload.get("incomplete_details"),
        "output": output_items,
        "usage": usage,
        "cached_tokens": cached,
        "text": output_text_of(output_items),
        "seconds": (finished - started).total_seconds(),
    }
    _append_log(
        {
            "ts": finished.isoformat(),
            "effort": effort,
            "call_type": call_type,
            "prompt_cache_key": body.get("prompt_cache_key"),
            "cached_tokens": cached,
            "request": body,
            "response": payload,
            "fallback": fallback,
        }
    )
    return result
