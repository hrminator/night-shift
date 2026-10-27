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
