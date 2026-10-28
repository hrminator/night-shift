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
SCAN_PNG_2X_NAME = "baltic_quote_Q-1187-B@2x.png"
SCAN_PNG_2X_PATH = FIXTURES / SCAN_PNG_2X_NAME
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


def build_grounding_input(png_path: Path | str, line_text: str, instruction_variant: str = "default") -> list:
    """One user message: the grounding instruction plus the PNG as a data URL."""
    raw = Path(png_path).read_bytes()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError(
            f"PNG is {len(raw)} bytes, over the {MAX_PNG_BYTES} inline limit")
    data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    if instruction_variant == "tight":
        target = f'the single line of text that reads: "{line_text}"'
    else:
        target = f'the text line reading exactly: "{line_text}"'
    return [{
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": (
                "You are an object grounding expert. Provide the bounding"
                f" box coordinates of {target}."
                " The coordinates should be in the 0-1000"
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
    instruction_variant: str = "default",
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
        build_grounding_input(png_path, line_text, instruction_variant),
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


def load_lines(path: Path | str = LINES_JSON_PATH) -> list:
    """The lines.json bands, or [] when the file is missing or broken."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict) and isinstance(data.get("lines"), list):
        return [entry for entry in data["lines"] if isinstance(entry, dict)]
    return data if isinstance(data, list) else []


def load_lines_doc(path: Path | str = LINES_JSON_PATH) -> dict:
    """The full lines.json document with its scale metadata."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"scale": 1, "lines": []}
    if isinstance(data, dict) and isinstance(data.get("lines"), list):
        return data
    if isinstance(data, list):
        return {"scale": 1, "lines": data}
    return {"scale": 1, "lines": []}


def lines_scale(path: Path | str = LINES_JSON_PATH) -> int:
    """The scale recorded in lines.json (1 for the 1x PNG)."""
    scale = load_lines_doc(path).get("scale", 1)
    return scale if isinstance(scale, int) else 1


def scale_band(band: dict, factor: int = 2) -> dict:
    """One band scaled by an integer factor (exact multiply)."""
    return {"text": band.get("text", ""),
            "y_top": band["y_top"] * factor,
            "y_bottom": band["y_bottom"] * factor,
            "x_left": band["x_left"] * factor,
            "x_right": band["x_right"] * factor}


def scaled_lines(factor: int = 2, lines: list | None = None) -> list:
    """Every 1x band scaled by an integer factor (exact multiply)."""
    entries = lines if lines is not None else load_lines()
    return [scale_band(entry, factor) for entry in entries
            if isinstance(entry, dict)
            and all(key in entry for key in
                    ("y_top", "y_bottom", "x_left", "x_right"))]


def find_band(line_text: str, lines: list | None = None) -> dict | None:
    """The lines.json band for one quoted line, if it names a line there."""
    want = str(line_text or "").strip()
    if not want:
        return None
    entries = lines if lines is not None else load_lines()
    for entry in entries:
        if isinstance(entry, dict) \
                and str(entry.get("text") or "").strip() == want:
            return entry
    folded = want.casefold()
    for entry in entries:
        if isinstance(entry, dict) \
                and str(entry.get("text") or "").strip().casefold() == folded:
            return entry
    return None


def png_size_of(path: Path | str = SCAN_PNG_PATH) -> tuple[int, int] | None:
    """Pixel size of the scan PNG, or None when it cannot be read."""
    try:
        from PIL import Image
        with Image.open(path) as shot:
            return (shot.size[0], shot.size[1])
    except (OSError, ValueError):
        return None


def score_box(bbox: dict, band: dict, png_size: tuple[int, int]) -> dict:
    """Score one 0-1000 box against a lines.json band, in PNG pixels.

    Pass: the box's vertical centre falls inside the band AND the box
    covers at least 70% of the line's width.
    """
    width, height = png_size
    x0 = bbox["x_min"] / 1000 * width
    x1 = bbox["x_max"] / 1000 * width
    centre_y = (bbox["y_min"] + bbox["y_max"]) / 2 / 1000 * height
    vertical = band["y_top"] <= centre_y <= band["y_bottom"]
    line_width = band["x_right"] - band["x_left"]
    overlap = max(0.0, min(x1, band["x_right"]) - max(x0, band["x_left"]))
    coverage = (overlap / line_width) if line_width > 0 else 0.0
    wide_enough = coverage >= 0.70
    return {"pass": bool(vertical and wide_enough), "centre_y": centre_y,
            "vertical": bool(vertical), "coverage": coverage,
            "wide_enough": bool(wide_enough)}


def score_line(
    bbox: dict | None,
    line_text: str,
    png_size: tuple[int, int] | None = None,
    lines: list | None = None,
) -> bool | None:
    """on_target for one box: None when lines.json has no such line."""
    try:
        if bbox is None:
            return None
        band = find_band(line_text, lines)
        if band is None:
            return None
        size = png_size or png_size_of()
        if size is None:
            return None
        return score_box(bbox, band, size)["pass"]
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
