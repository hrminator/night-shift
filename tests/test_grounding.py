"""B1 grounding: fixture PNG + line bands, the grounding call, scoring.

Part 1 (no model): the scan-styled fixture also ships its exact PNG plus
one pixel band per rendered line. Part 2 (fake respond): after the
reassess turn, one grounding call locates the quoted line, or a
line_not_located event records the failure.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from scripts.make_fixtures import REVISED_LINES

FIXTURES = Path("fixtures")
SCAN_PNG = FIXTURES / "baltic_quote_Q-1187-B.png"
LINES_JSON = FIXTURES / "baltic_quote_Q-1187-B.lines.json"


def _bands() -> list:
    return json.loads(LINES_JSON.read_text(encoding="utf-8"))


def test_lines_json_has_one_entry_per_rendered_line():
    bands = _bands()
    assert [entry["text"] for entry in bands] == REVISED_LINES


def test_arrival_line_band_inside_page():
    bands = _bands()
    with Image.open(SCAN_PNG) as shot:
        width, height = shot.size
    arrival = next(
        entry for entry in bands if "warehouse" in entry["text"])
    assert arrival["text"] == (
        "Delivery: Goods will leave our warehouse by 10 November.")
    assert 0 <= arrival["x_left"] < arrival["x_right"] <= width
    assert 0 <= arrival["y_top"] < arrival["y_bottom"] <= height
