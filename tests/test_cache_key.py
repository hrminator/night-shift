"""Prompt-cache key and cached-token pricing (pure code, no model).

respond() sends prompt_cache_key (nightshift-<instrhash>-<call_type>) and
prompt_cache_retention on every request; the key is stable for one call
type and distinct across call types; cached tokens reach the spend ledger
at the cached price.
"""

from __future__ import annotations

import hashlib
import re

import app.adapter as adapter
from app.spend import SpendCap, call_with_cap, cost_usd, usage_of
from app.store import day_spend_usd, record_spend

INSTRUCTIONS = "You are Night Shift. Read the sources and record claims."


class _FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, usage):
        self._usage = usage

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "model": "muse-spark-1.3-test",
            "id": "resp-1",
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "hi"}]}],
            "usage": self._usage,
        }


def _usage():
    return {"input_tokens": 1000, "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 800}}


def _capture(monkeypatch):
    seen = {}

    def fake_post(body, timeout):
        seen["body"] = body
        seen["timeout"] = timeout
        return _FakeResponse(_usage())

    def fake_log(record, path=None):
        seen["log"] = record

    monkeypatch.setattr(adapter, "_post", fake_post)
    monkeypatch.setattr(adapter, "_append_log", fake_log)
    return seen


def test_respond_sends_cache_fields_with_expected_key_format(monkeypatch):
    seen = _capture(monkeypatch)
    result = adapter.respond(INSTRUCTIONS, "hello", call_type="read")
    body = seen["body"]
    instrhash = hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()[:12]
    assert body["prompt_cache_key"] == f"nightshift-{instrhash}-read"
    assert re.fullmatch(r"nightshift-[0-9a-f]{12}-read",
                        body["prompt_cache_key"])
    assert body["prompt_cache_retention"] == "24h"
    assert result["cached_tokens"] == 800
    assert seen["log"]["cached_tokens"] == 800
    assert seen["log"]["call_type"] == "read"
    assert seen["log"]["prompt_cache_key"] == body["prompt_cache_key"]


def test_key_stable_per_type_and_distinct_across_types():
    first = adapter.build_request(INSTRUCTIONS, "a", call_type="read")
    second = adapter.build_request(INSTRUCTIONS, "b", call_type="read")
    assert first["prompt_cache_key"] == second["prompt_cache_key"]
    for other in ("reassess", "resume", "decision", "extract"):
        assert adapter.build_request(
            INSTRUCTIONS, "a", call_type=other)["prompt_cache_key"] != \
            first["prompt_cache_key"]
    assert adapter.build_request(
        INSTRUCTIONS + " ", "a",
        call_type="read")["prompt_cache_key"] != first["prompt_cache_key"]
    assert adapter.prompt_cache_key_for(
        INSTRUCTIONS, "read") == first["prompt_cache_key"]


def test_cached_tokens_flow_into_spend_at_cached_price(tmp_path, monkeypatch):
    """Fake respond function, no network: cached input is priced at $0.15/M."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_respond(instructions, input_items, **kwargs):
        return {"output": [], "text": "",
                "usage": {"input_tokens": 1000, "output_tokens": 100,
                          "input_tokens_details": {"cached_tokens": 800}}}

    cap = SpendCap(10.0)
    result = call_with_cap(fake_respond, cap, 0.01, INSTRUCTIONS, "hi",
                           call_type="read")
    assert result["capped"] is True
    inputs, cached, outputs = usage_of(result)
    assert (inputs, cached, outputs) == (1000, 800, 100)
    assert cap.spent_usd == cost_usd(1000, 800, 100) == 0.000795
    assert cap.spent_usd < cost_usd(1000, 0, 100)

    record_spend("2026-10-28", "job-cache", "test-call", inputs, cached,
                 outputs, cost_usd(inputs, cached, outputs))
    assert day_spend_usd("2026-10-28") == cost_usd(1000, 800, 100)
