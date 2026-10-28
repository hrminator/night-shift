"""B1 grounding: fixture PNG + line bands, the grounding call, scoring.

Part 1 (no model): the scan-styled fixture also ships its exact PNG plus
one pixel band per rendered line. Part 2 (fake respond): after the
reassess turn, one grounding call locates the quoted line, or a
line_not_located event records the failure.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app.adapter as adapter_mod
import app.grounding as grounding_mod
import app.main as main_mod
import app.runner as runner_mod
from app.store import append_event, create_job, list_events
from scripts.make_fixtures import REVISED_LINES

FIXTURES = Path("fixtures")
SCAN_PNG = FIXTURES / "baltic_quote_Q-1187-B.png"
SCAN_PNG_2X = FIXTURES / "baltic_quote_Q-1187-B@2x.png"
LINES_JSON = FIXTURES / "baltic_quote_Q-1187-B.lines.json"


def _bands() -> list:
    data = json.loads(LINES_JSON.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data["lines"]
    return data


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


def test_lines_json_records_scale_1():
    doc = json.loads(LINES_JSON.read_text(encoding="utf-8"))
    assert doc["scale"] == 1
    assert doc["png"] == "baltic_quote_Q-1187-B.png"
    with Image.open(SCAN_PNG) as shot:
        assert doc["png_size"] == [shot.size[0], shot.size[1]]
    assert grounding_mod.lines_scale() == 1


def test_2x_band_equals_1x_times_2_for_every_line():
    bands_1x = _bands()
    bands_2x = grounding_mod.scaled_lines(2, bands_1x)
    assert len(bands_2x) == len(bands_1x) == len(REVISED_LINES)
    with Image.open(SCAN_PNG) as shot_1x:
        size_1x = shot_1x.size
    with Image.open(SCAN_PNG_2X) as shot_2x:
        size_2x = shot_2x.size
    assert size_2x == (size_1x[0] * 2, size_1x[1] * 2)
    assert size_2x == (1190, 1682)
    for one, two in zip(bands_1x, bands_2x):
        assert two["text"] == one["text"]
        assert two["y_top"] == one["y_top"] * 2
        assert two["y_bottom"] == one["y_bottom"] * 2
        assert two["x_left"] == one["x_left"] * 2
        assert two["x_right"] == one["x_right"] * 2
        assert 0 <= two["x_left"] < two["x_right"] <= size_2x[0]
        assert 0 <= two["y_top"] < two["y_bottom"] <= size_2x[1]


ARRIVAL_LINE = "Delivery: Goods will leave our warehouse by 10 November."


def _scan_job(tmp_path, monkeypatch, quote=ARRIVAL_LINE):
    """A night whose reassess claims include the Q-1187-B scan quote."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GROUNDING_ENABLED", raising=False)
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    append_event(job["id"], "00:39", "claim", {
        "source": "Baltic revised Q-1187-B",
        "version_or_file_id": "Q-1187-B",
        "quote": quote,
        "claim": "dispatch-only, no arrival date",
    })
    append_event(job["id"], "00:39", "decision", {
        "outcome": "wake", "reason": "stub", "evidence": []})
    return job["id"]


def _ground_result(text, **extra):
    result = {"output": [], "text": text, "model": "muse-spark-1.3-test",
              "response_id": "resp-ground-1", "seconds": 1.2,
              "usage": {"input_tokens": 100, "output_tokens": 10}}
    result.update(extra)
    return result


def _grounding_kinds(job_id):
    return [event for event in list_events(job_id)
            if event["kind"] in ("line_located", "line_not_located")]


def _grid_box_for(band: dict, size: tuple) -> dict:
    """The band itself, expressed as a 0-1000 box (an on-target answer)."""
    width, height = size
    return {
        "x_min": int(band["x_left"] / width * 1000),
        "y_min": int(band["y_top"] / height * 1000),
        "x_max": int(band["x_right"] / width * 1000),
        "y_max": int(band["y_bottom"] / height * 1000),
    }


def test_grounding_call_writes_line_located(tmp_path, monkeypatch):
    job_id = _scan_job(tmp_path, monkeypatch)
    seen: dict = {}
    calls: list = []
    band = grounding_mod.find_band(ARRIVAL_LINE)
    assert band is not None
    box = _grid_box_for(band,
                        grounding_mod.png_size_of(SCAN_PNG))

    def fake_respond(instructions, input_items, **kwargs):
        calls.append(1)
        seen["instructions"] = instructions
        seen["input"] = input_items
        seen["kwargs"] = kwargs
        return _ground_result(json.dumps({
            "object_name": "quoted line", "bbox": [box]}))

    event = runner_mod.maybe_ground_scan_line(job_id,
                                              respond_fn=fake_respond)
    assert event is not None and event["kind"] == "line_located"
    payload = event["payload"]
    assert payload["bbox"] == box
    assert payload["line_text"] == ARRIVAL_LINE
    assert payload["png"] == "baltic_quote_Q-1187-B.png"
    assert payload["model"] == "muse-spark-1.3-test"
    assert payload["response_id"] == "resp-ground-1"
    assert payload["seconds"] == 1.2
    assert payload["on_target"] is True
    claims = [entry for entry in list_events(job_id)
              if entry["kind"] == "claim"]
    assert payload["claim_id"] == claims[-1]["id"]
    content = seen["input"][0]["content"]
    texts = [part["text"] for part in content
             if part["type"] == "input_text"]
    images = [part for part in content if part["type"] == "input_image"]
    assert len(images) == 1
    assert images[0]["image_url"].startswith("data:image/png;base64,")
    sent_png = base64.b64decode(images[0]["image_url"].split(",", 1)[1])
    assert sent_png == SCAN_PNG.read_bytes()
    assert ARRIVAL_LINE in texts[0]
    assert "0-1000" in texts[0]
    assert seen["kwargs"]["call_type"] == "ground"
    assert seen["kwargs"]["text_format"]["type"] == "json_schema"
    assert "grounding expert" in seen["instructions"].lower()
    assert runner_mod.maybe_ground_scan_line(
        job_id, respond_fn=fake_respond) is None
    assert len(calls) == 1
    assert len(_grounding_kinds(job_id)) == 1


def test_tight_variant_names_a_single_line():
    default = grounding_mod.build_grounding_input(SCAN_PNG_2X, ARRIVAL_LINE)
    tight = grounding_mod.build_grounding_input(
        SCAN_PNG_2X, ARRIVAL_LINE, "tight")
    default_text = default[0]["content"][0]["text"]
    tight_text = tight[0]["content"][0]["text"]
    assert "text line reading exactly" in default_text
    assert "the single line of text that reads:" in tight_text
    assert ARRIVAL_LINE in tight_text
    assert "0-1000" in tight_text


def test_grounding_clamps_to_0_1000(tmp_path, monkeypatch):
    job_id = _scan_job(tmp_path, monkeypatch)

    def fake_respond(instructions, input_items, **kwargs):
        return _ground_result(json.dumps({
            "object_name": "quoted line",
            "bbox": [{"x_min": -5, "y_min": 311,
                      "x_max": 1001, "y_max": 333}]}))

    event = runner_mod.maybe_ground_scan_line(job_id,
                                              respond_fn=fake_respond)
    assert event["payload"]["bbox"] == {"x_min": 0, "y_min": 311,
                                        "x_max": 1000, "y_max": 333}


def test_grounding_failure_writes_line_not_located(tmp_path, monkeypatch):
    job_id = _scan_job(tmp_path, monkeypatch)

    def boom(instructions, input_items, **kwargs):
        raise RuntimeError("transport down")

    event = runner_mod.maybe_ground_scan_line(job_id, respond_fn=boom)
    assert event is not None and event["kind"] == "line_not_located"
    assert event["payload"]["line_text"] == ARRIVAL_LINE
    assert event["payload"]["reason"].startswith("exception: RuntimeError")


def test_grounding_empty_result_writes_line_not_located(tmp_path,
                                                        monkeypatch):
    for text in ("", json.dumps({"object_name": "quoted line", "bbox": []})):
        job_id = _scan_job(tmp_path, monkeypatch)

        def fake_respond(instructions, input_items, _text=text, **kwargs):
            return _ground_result(_text)

        event = runner_mod.maybe_ground_scan_line(job_id,
                                                  respond_fn=fake_respond)
        assert event is not None and event["kind"] == "line_not_located"
        assert event["payload"]["line_text"] == ARRIVAL_LINE
        assert event["payload"]["reason"] == "no_box"


def test_night_without_scan_claim_makes_no_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GROUNDING_ENABLED", raising=False)
    job = create_job(status="running", current_step="reassess",
                     virtual_time="00:39")
    append_event(job["id"], "00:39", "claim", {
        "source": "Vestland portal record",
        "quote": "Wed Nov 11 08:00-12:00", "claim": "van guaranteed"})
    calls: list = []

    def fake_respond(instructions, input_items, **kwargs):
        calls.append(1)
        raise AssertionError("must not be called")

    assert runner_mod.maybe_ground_scan_line(
        job["id"], respond_fn=fake_respond) is None
    assert calls == []
    assert _grounding_kinds(job["id"]) == []


def test_grounding_flag_off_makes_no_call(tmp_path, monkeypatch):
    job_id = _scan_job(tmp_path, monkeypatch)
    monkeypatch.setenv("GROUNDING_ENABLED", "0")

    def fake_respond(instructions, input_items, **kwargs):
        raise AssertionError("must not be called")

    assert runner_mod.maybe_ground_scan_line(
        job_id, respond_fn=fake_respond) is None
    assert _grounding_kinds(job_id) == []


def test_adapter_sends_text_format_with_store_false():
    body = adapter_mod.build_request(
        "instr", "hi", call_type="ground",
        text_format=grounding_mod.GROUNDING_FORMAT)
    assert body["store"] is False
    assert body["text"] == {"format": grounding_mod.GROUNDING_FORMAT}
    assert "previous_response_id" not in body
    assert body["prompt_cache_key"].endswith("-ground")
    plain = adapter_mod.build_request("instr", "hi", call_type="read")
    assert "text" not in plain


def test_locate_line_logs_through_adapter(monkeypatch):
    seen: dict = {}

    class _FakeResponse:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "muse-spark-1.3-test", "id": "resp-log-1",
                "status": "completed",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps({
                        "object_name": "quoted line",
                        "bbox": [{"x_min": 1, "y_min": 2,
                                  "x_max": 3, "y_max": 4}]})}]}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

    def fake_post(body, timeout):
        seen["body"] = body
        return _FakeResponse()

    def fake_log(record, path=None):
        seen["log"] = record

    monkeypatch.setattr(adapter_mod, "_post", fake_post)
    monkeypatch.setattr(adapter_mod, "_append_log", fake_log)
    bbox = grounding_mod.locate_line(SCAN_PNG, ARRIVAL_LINE)
    assert bbox == {"x_min": 1, "y_min": 2, "x_max": 3, "y_max": 4}
    assert seen["body"]["store"] is False
    assert seen["body"]["max_output_tokens"] == 2048
    assert seen["body"]["text"]["format"]["type"] == "json_schema"
    assert seen["log"]["call_type"] == "ground"
    assert seen["log"]["response"]["id"] == "resp-log-1"


ARRIVAL_BAND = {"y_top": 311, "y_bottom": 333,
                "x_left": 66, "x_right": 384}
ARRIVAL_SIZE = (595, 841)


def test_score_box_passes_on_target():
    verdict = grounding_mod.score_box(
        {"x_min": 120, "y_min": 372, "x_max": 640, "y_max": 394},
        ARRIVAL_BAND, ARRIVAL_SIZE)
    assert verdict["pass"] is True
    assert verdict["vertical"] is True
    assert verdict["wide_enough"] is True


def test_score_box_fails_vertical_miss():
    verdict = grounding_mod.score_box(
        {"x_min": 120, "y_min": 100, "x_max": 640, "y_max": 200},
        ARRIVAL_BAND, ARRIVAL_SIZE)
    assert verdict["pass"] is False
    assert verdict["vertical"] is False


def test_score_box_fails_narrow_box():
    verdict = grounding_mod.score_box(
        {"x_min": 110, "y_min": 372, "x_max": 200, "y_max": 394},
        ARRIVAL_BAND, ARRIVAL_SIZE)
    assert verdict["pass"] is False
    assert verdict["vertical"] is True
    assert verdict["wide_enough"] is False


def test_score_line_unknown_line_is_none():
    assert grounding_mod.score_line(
        {"x_min": 120, "y_min": 372, "x_max": 640, "y_max": 394},
        "no such line on the page", ARRIVAL_SIZE) is None
    assert grounding_mod.score_line(None, ARRIVAL_LINE,
                                    ARRIVAL_SIZE) is None


def test_find_band_matches_exact_and_case():
    lines = [{"text": ARRIVAL_LINE, "y_top": 1, "y_bottom": 2,
              "x_left": 3, "x_right": 4}]
    assert grounding_mod.find_band(ARRIVAL_LINE, lines) == lines[0]
    assert grounding_mod.find_band("  " + ARRIVAL_LINE + "  ",
                                   lines) == lines[0]
    assert grounding_mod.find_band(ARRIVAL_LINE.lower(),
                                   lines) == lines[0]
    assert grounding_mod.find_band("missing", lines) is None


LOCATED_BOX = {"x_min": 108, "y_min": 382, "x_max": 688, "y_max": 399}


def _located_event():
    return {"id": 90, "job_id": "job-ground", "seq": 90,
            "virtual_time": "00:39", "kind": "line_located",
            "payload": {"claim_id": 80, "line_text": ARRIVAL_LINE,
                        "bbox": dict(LOCATED_BOX),
                        "png": "baltic_quote_Q-1187-B@2x.png",
                        "model": "muse-spark-1.3-test",
                        "response_id": "resp-g", "seconds": 1.0,
                        "on_target": True},
            "created_at": "2026-10-28T00:00:00+00:00"}


def _unlocated_event():
    event = _located_event()
    event["kind"] = "line_not_located"
    event["payload"] = {"claim_id": 80, "line_text": ARRIVAL_LINE,
                        "reason": "no_box"}
    return event


def _pass_verdict(monkeypatch):
    monkeypatch.setattr(main_mod, "_grounding_verdict",
                        lambda: {"verdict": "PASS", "passed": 9,
                                 "runs": 10})


def _fail_verdict(monkeypatch):
    monkeypatch.setattr(main_mod, "_grounding_verdict",
                        lambda: {"verdict": "FAIL", "passed": 7,
                                 "runs": 10})


def test_scan_section_draws_box_when_verdict_pass(monkeypatch):
    _pass_verdict(monkeypatch)
    html = main_mod.scan_grounding_section([_located_event()])
    assert "Muse Spark located the line it quoted " \
        "(grounding call; 9 of 10 probes on target)" in html
    assert "outline:3px solid #f59e0b" in html
    assert "left:10.8%;top:38.2%;width:58.0%;height:1.7%" in html
    assert "data:image/png;base64," in html
    assert ARRIVAL_LINE in html
    assert "not a real scan" in html


def test_scan_section_underlines_when_verdict_fail(monkeypatch):
    _fail_verdict(monkeypatch)
    html = main_mod.scan_grounding_section([_located_event()])
    assert "<p>Line Muse Spark quoted</p>" in html
    assert "#f59e0b" not in html
    assert "border-top:3px solid #1d4ed8" in html
    band = grounding_mod.find_band(ARRIVAL_LINE)
    size = grounding_mod.png_size_of()
    expect = (f"left:{band['x_left'] / size[0] * 100:.1f}%;"
              f"top:{band['y_bottom'] / size[1] * 100:.1f}%;"
              f"width:{(band['x_right'] - band['x_left']) / size[0] * 100:.1f}%")
    assert expect in html


def test_scan_section_underlines_when_not_located(monkeypatch):
    _pass_verdict(monkeypatch)
    html = main_mod.scan_grounding_section([_unlocated_event()])
    assert "<p>Line Muse Spark quoted</p>" in html
    assert "#f59e0b" not in html


def test_scan_section_empty_without_grounding_event():
    assert main_mod.scan_grounding_section([]) == ""
    claim = {"id": 80, "job_id": "job-ground", "seq": 80,
             "virtual_time": "00:39", "kind": "claim",
             "payload": {"source": "Baltic revised Q-1187-B",
                         "quote": ARRIVAL_LINE, "claim": "x"},
             "created_at": "2026-10-28T00:00:00+00:00"}
    assert main_mod.scan_grounding_section([claim]) == ""
    morning = main_mod.render_morning_page("Job job-ground", [claim])
    assert "Revised quote: the line it quoted" not in morning


def test_morning_page_shows_scan_section(monkeypatch):
    _fail_verdict(monkeypatch)
    morning = main_mod.render_morning_page("Job job-ground",
                                           [_unlocated_event()])
    assert "<p>Line Muse Spark quoted</p>" in morning
    assert "data:image/png;base64," in morning


def test_job_page_shows_scan_section(tmp_path, monkeypatch):
    _fail_verdict(monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = create_job(status="done", current_step="done",
                     virtual_time="07:00")
    append_event(job["id"], "00:39", "claim", {
        "source": "Baltic revised Q-1187-B", "quote": ARRIVAL_LINE,
        "claim": "dispatch-only"})
    append_event(job["id"], "00:39", "line_not_located", {
        "claim_id": 1, "line_text": ARRIVAL_LINE, "reason": "no_box"})
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get(f"/jobs/{job['id']}")
    assert response.status_code == 200
    assert "<p>Line Muse Spark quoted</p>" in response.text
    assert "grounding: line not located (no_box)" in response.text


def test_front_door_uses_recorded_job_event(tmp_path, monkeypatch):
    _pass_verdict(monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    handoff = {"id": 1, "job_id": "groundrec", "seq": 1,
               "virtual_time": "21:30", "kind": "handoff",
               "payload": {"brief": "fixtures/brief.md", "source": "owner",
                           "variant": "hero"},
               "created_at": "2026-10-28T00:00:00+00:00"}
    checkpoint = {"id": 95, "job_id": "groundrec", "seq": 95,
                  "virtual_time": "00:47", "kind": "checkpoint",
                  "payload": {"question_event_id": 0, "next_input": []},
                  "created_at": "2026-10-28T00:01:00+00:00"}
    record = {"job_id": "groundrec", "exported": True,
              "events": [handoff, _located_event(), checkpoint]}
    (runs / "job-groundrec.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RECORDED_JOB", "groundrec")
    body = main_mod.index()
    assert "9 of 10 probes on target" in body
    assert "outline:3px solid #f59e0b" in body


def test_summarize_grounding_kinds():
    assert "located" in main_mod._summarize(
        "line_located", {"bbox": dict(LOCATED_BOX)})
    assert "no_box" in main_mod._summarize(
        "line_not_located", {"reason": "no_box"})
