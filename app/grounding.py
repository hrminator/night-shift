"""One object-grounding call per night: point at the line Spark quoted.

After the reassess turn has written its decision record for a night in
which the revised quote Q-1187-B (the scan-styled, image-only PDF) was
read, the app sends the rendered page as a PNG plus "locate this line",
using the exact line text Spark quoted in its claim about the revised
quote. The call runs outside the model's decision context, behind the
GROUNDING_ENABLED flag, and failure is tolerated: a failed, empty or
off-target result logs ``line_not_located`` and changes nothing else.

This call does not detect the change; Spark found the change in its own
reading of the page during the reassess turn. B1 only points at the line
Spark quoted.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path

from app import adapter

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SCAN_PNG_NAME = "baltic_quote_Q-1187-B.png"
SCAN_PNG_PATH = FIXTURES / SCAN_PNG_NAME
LINES_JSON_NAME = "baltic_quote_Q-1187-B.lines.json"
LINES_JSON_PATH = FIXTURES / LINES_JSON_NAME

#: Inline PNG limit from Meta's vision docs.
MAX_PNG_BYTES = 50 * 1024 * 1024

GROUNDING_CALL_TYPE = "ground"
GROUNDING_EFFORT = "low"
GROUNDING_MAX_OUTPUT_TOKENS = 2048

#: Minimal system prompt; the grounding instruction goes in the message.
GROUNDING_INSTRUCTIONS = "You are an object grounding expert."

#: text.format schema: one named object with a list of 0-1000 bboxes.
GROUNDING_FORMAT = {
    "type": "json_schema",
    "name": "line_location",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "bbox": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x_min": {"type": "integer"},
                        "y_min": {"type": "integer"},
                        "x_max": {"type": "integer"},
                        "y_max": {"type": "integer"},
                    },
                    "required": ["x_min", "y_min", "x_max", "y_max"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["object_name", "bbox"],
        "additionalProperties": False,
    },
}


def build_grounding_input(png_path: Path | str, line_text: str) -> list:
    """One user message: the grounding instruction plus the PNG as a data URL."""
    raw = Path(png_path).read_bytes()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError(
            f"PNG is {len(raw)} bytes, over the {MAX_PNG_BYTES} inline limit")
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    return [{
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": (
                "You are an object grounding expert. Provide the bounding"
                " box coordinates of the text line reading exactly:"
                f' "{line_text}". The coordinates should be in the 0-1000'
                " range with (0, 0) at the top left. If you cannot find an"
                " object, omit it."
            )},
            {"type": "input_image", "image_url": data_url},
        ],
    }]


def parse_bbox(text: str) -> dict | None:
    """First bbox from the grounding JSON, clamped to 0-1000 ints.

    Returns None when the text is empty, is not JSON, or names no box
    (the model omits what it cannot find).
    """
    try:
        payload = json.loads(text or "")
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    boxes = payload.get("bbox")
    if not isinstance(boxes, list) or not boxes:
        return None
    first = boxes[0]
    if not isinstance(first, dict):
        return None
    try:
        values = {
            key: int(float(first[key]))
            for key in ("x_min", "y_min", "x_max", "y_max")
        }
    except (KeyError, TypeError, ValueError):
        return None
    return {key: max(0, min(1000, value)) for key, value in values.items()}


def locate_line(
    png_path: Path | str,
    line_text: str,
    call_type: str = GROUNDING_CALL_TYPE,
    *,
    effort: str = GROUNDING_EFFORT,
    respond_fn: Callable[..., dict] | None = None,
) -> dict | None:
    """Locate one quoted line on the scan page; None when not found.

    Sends our own PNG (not the PDF: the file endpoint returns no
    coordinates) plus "locate this line" through the adapter, so the raw
    response is logged like every other call. A failed call raises to the
    caller; an empty, omitted or unparseable result returns None.
    """
    responder = respond_fn or adapter.respond
    result = responder(
        GROUNDING_INSTRUCTIONS,
        build_grounding_input(png_path, line_text),
        effort=effort,
        max_output_tokens=GROUNDING_MAX_OUTPUT_TOKENS,
        call_type=call_type,
        text_format=GROUNDING_FORMAT,
    )
    return parse_bbox((result or {}).get("text") or "")


def is_scan_claim(event: dict) -> bool:
    """True when a claim event's source is the Q-1187-B scan-styled page."""
    if (event or {}).get("kind") != "claim":
        return False
    payload = event.get("payload") or {}
    source = str(payload.get("source") or "")
    version = str(payload.get("version_or_file_id") or "")
    return "1187-b" in source.lower() or "1187-b" in version.lower()


def pick_scan_claim(events: list) -> dict | None:
    """The last scan claim with a quoted line, if the night has one."""
    candidates = [
        event for event in events
        if is_scan_claim(event)
        and str((event.get("payload") or {}).get("quote") or "").strip()
    ]
    return candidates[-1] if candidates else None
