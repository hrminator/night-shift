from app.adapter import (
    MODEL,
    build_request,
    drop_reasoning_items,
    output_text_of,
    reasoning_items_of,
)


def test_request_carries_replay_fields_and_no_resume_id():
    body = build_request("do this", "hello", effort="low", max_output_tokens=64)
    assert body["model"] == MODEL
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 64
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is True
    assert "previous_response_id" not in body


def test_instructions_tools_and_effort_are_resent_each_call():
    tools = [{"type": "function", "name": "ping"}]
    first = build_request("a", "x", tools=tools, effort="minimal")
    second = build_request("a", "x", tools=tools, effort="minimal")
    assert first["instructions"] == second["instructions"] == "a"
    assert first["tools"] == second["tools"] == tools
    assert first["reasoning"] == second["reasoning"] == {"effort": "minimal"}


def test_reasoning_items_kept_in_order_and_droppable_whole():
    output = [
        {"type": "reasoning", "id": "r1", "encrypted_content": "abc"},
        {"type": "message", "content": [{"type": "output_text", "text": "hi"}]},
        {"type": "reasoning", "id": "r2", "encrypted_content": "def"},
    ]
    assert [i["id"] for i in reasoning_items_of(output)] == ["r1", "r2"]
    assert output_text_of(output) == "hi"
    dropped = drop_reasoning_items(output)
    assert [i.get("type") for i in dropped] == ["message"]
    # The surviving message item is untouched.
    assert dropped[0]["content"][0]["text"] == "hi"


def test_api_key_prefers_live_over_eval(monkeypatch):
    import app.adapter as adapter

    monkeypatch.setenv("NIGHT_SHIFT_API_KEY_LIVE", "live-key")
    monkeypatch.setenv("NIGHT_SHIFT_API_KEY_EVAL", "eval-key")
    assert adapter.api_key() == "live-key"


def test_api_key_falls_back_to_eval(monkeypatch):
    import app.adapter as adapter

    monkeypatch.delenv("NIGHT_SHIFT_API_KEY_LIVE", raising=False)
    monkeypatch.setenv("NIGHT_SHIFT_API_KEY_EVAL", "eval-key")
    assert adapter.api_key() == "eval-key"


def test_api_key_reads_live_only(monkeypatch):
    import app.adapter as adapter

    monkeypatch.setenv("NIGHT_SHIFT_API_KEY_LIVE", "live-key")
    monkeypatch.delenv("NIGHT_SHIFT_API_KEY_EVAL", raising=False)
    assert adapter.api_key() == "live-key"


def test_api_key_error_names_both_vars(monkeypatch):
    import pytest

    import app.adapter as adapter

    monkeypatch.delenv("NIGHT_SHIFT_API_KEY_LIVE", raising=False)
    monkeypatch.delenv("NIGHT_SHIFT_API_KEY_EVAL", raising=False)
    with pytest.raises(RuntimeError, match="NIGHT_SHIFT_API_KEY_LIVE"):
        adapter.api_key()
    try:
        adapter.api_key()
    except RuntimeError as exc:
        assert "NIGHT_SHIFT_API_KEY_EVAL" in str(exc)
    else:  # pragma: no cover - api_key must raise when both are missing
        raise AssertionError("api_key() did not raise with no keys set")
