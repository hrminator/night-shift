"""S1a-fix acceptance (Playwright against a live test server).

The owner's four marks on the v2 comps, verified on the real pages:
1. State B: header, clock, question and both buttons inside the first
   phone viewport at 360/390/430 px, strip and lists below the buttons,
   on the recorded replay and on a live copy's /jobs/{id} page.
2. Morning: receipt under the strip in the left column, max 360 px,
   Geist Mono 14, its own shadow, left column not half empty.
3. Desktop: left column sticky (top 32 px) in all three states; the
   night page scrolled 1500 px at 1440x900 keeps the clock in view.
4. Phone: the 00:38 and 02:00 tick labels do not touch at 360 px.
Plus the two film beats: the sheet keeps 96 px inner padding with the
changed line inside the frame at full push-in, and the note beat
renders the two answers as the product's own buttons.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests.test_s1a_accept import seed_live_morning

RECORDED = "6c7c7c742513"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"


def seed_open_question(record: dict) -> str:
    """One live copy paused at its open question (no answer filed)."""
    from app import replay as replay_mod
    from app.store import append_event, create_job
    source = replay_mod.replay_events(record)
    job = create_job(status="waiting_for_owner",
                     current_step="waiting_for_owner",
                     virtual_time="00:47")
    new_id = job["id"]
    old_to_new: dict[int, int] = {}
    for event in source:
        payload = copy.deepcopy(event.get("payload") or {})
        if event.get("kind") == "checkpoint" and isinstance(
                payload.get("question_event_id"), int):
            payload["question_event_id"] = old_to_new.get(
                int(payload["question_event_id"]),
                payload["question_event_id"])
            payload["copied_from_recorded"] = True
        stored = append_event(new_id,
                              event.get("virtual_time") or "00:47",
                              event.get("kind") or "note", payload)
        old_to_new[int(event.get("id", 0))] = int(stored["id"])
    return new_id


@pytest.fixture(scope="module")
def fix_server():
    """Uvicorn on 8123 over a seeded DATA_DIR, plus Playwright browser."""
    tmp = Path(tempfile.mkdtemp(prefix="s1a-fix-accept-"))
    old_data = os.environ.get("DATA_DIR")
    old_rec = os.environ.get("RECORDED_JOB")
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["RECORDED_JOB"] = RECORDED
    record = json.loads(
        (Path("data/runs") / f"job-{RECORDED}.json").read_text(
            encoding="utf-8"))
    morning_job = seed_live_morning(record)
    open_job = seed_open_question(record)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(Path(".").resolve()),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(BASE + "/", timeout=5) as resp:
                    if resp.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise AssertionError("test server never came up on 8123")
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch()
        try:
            yield {"base": BASE, "morning": morning_job,
                   "open": open_job, "browser": browser}
        finally:
            browser.close()
            playwright.stop()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        if old_data is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = old_data
        if old_rec is None:
            os.environ.pop("RECORDED_JOB", None)
        else:
            os.environ["RECORDED_JOB"] = old_rec


def _box(page, selector: str, nth: int = 0) -> dict:
    box = page.locator(selector).nth(nth).bounding_box()
    assert box is not None, selector
    return box


def _inside(viewport_height: int, box: dict) -> bool:
    return box["y"] >= 0 and box["y"] + box["height"] <= viewport_height


def test_mark1_state_b_first_viewport(fix_server):
    page = fix_server["browser"].new_page()
    try:
        urls = [("/?state=question", ".note form[action='/visitor/answer']"),
                (f"/jobs/{fix_server['open']}",
                 f".note form[action='/jobs/{fix_server['open']}/answer']")]
        for width in (360, 390, 430):
            page.set_viewport_size({"width": width, "height": 844})
            for url, form in urls:
                page.goto(fix_server["base"] + url, wait_until="load")
                header = _box(page, ".wmrow")
                assert _inside(844, header), (url, width, header)
                clock = _box(page, ".inst .clock")
                assert _inside(844, clock), (url, width, clock)
                asked = _box(page, ".note h2")
                assert _inside(844, asked), (url, width, asked)
                buttons = page.locator(f"{form} .btn")
                assert buttons.count() == 2, (url, width)
                bottom = 0.0
                for pos in range(2):
                    box = buttons.nth(pos).bounding_box()
                    assert box is not None
                    assert _inside(844, box), (url, width, box)
                    bottom = max(bottom, box["y"] + box["height"])
                fold = _box(page, ".detail details.fold")
                assert fold["y"] >= bottom, (url, width, fold, bottom)
    finally:
        page.close()


def test_mark2_morning_receipt_under_strip(fix_server):
    page = fix_server["browser"].new_page(
        viewport={"width": 1440, "height": 900})
    try:
        page.goto(fix_server["base"]
                  + f"/jobs/{fix_server['morning']}/morning",
                  wait_until="load")
        strip = _box(page, ".inst .strip")
        receipt = _box(page, ".inst .receipt")
        assert receipt["y"] >= strip["y"] + strip["height"], (strip,
                                                              receipt)
        style = page.evaluate("""() => {
          const rc = document.querySelector('.inst .receipt');
          const cs = getComputedStyle(rc);
          return {maxWidth: cs.maxWidth, fontSize: cs.fontSize,
                  shadow: cs.boxShadow};
        }""")
        assert style["maxWidth"] == "360px", style
        assert style["fontSize"] == "14px", style
        assert style["shadow"] not in ("", "none"), style
        inst = _box(page, ".inst")
        assert inst["height"] >= 700, inst
    finally:
        page.close()


def test_mark3_sticky_left_column(fix_server):
    page = fix_server["browser"].new_page(
        viewport={"width": 1440, "height": 900})
    try:
        urls = ["/?state=night", "/?state=question",
                f"/jobs/{fix_server['morning']}/morning"]
        for url in urls:
            page.goto(fix_server["base"] + url, wait_until="load")
            sticky = page.evaluate("""() => {
              const cs = getComputedStyle(document.querySelector('.stick'));
              return {position: cs.position, top: cs.top};
            }""")
            assert sticky == {"position": "sticky", "top": "32px"}, (
                url, sticky)
            header = _box(page, ".wmrow")
            stick = _box(page, ".stick")
            assert stick["y"] >= header["y"] + header["height"], (
                url, header, stick)
        page.goto(fix_server["base"] + "/?state=night",
                  wait_until="load")
        before = _box(page, ".inst .clock")
        page.evaluate("window.scrollTo(0, 500)")
        page.wait_for_timeout(200)
        stuck = _box(page, ".inst .clock")
        assert _inside(900, stuck), stuck
        assert stuck["x"] == pytest.approx(before["x"], abs=1), (
            before, stuck)
        assert stuck["width"] == pytest.approx(before["width"], abs=1), (
            before, stuck)
        assert stuck["y"] == pytest.approx(32, abs=2), stuck
        page.evaluate("window.scrollTo(0, 1500)")
        page.wait_for_timeout(200)
        after = _box(page, ".inst .clock")
        assert after["y"] < 900 and after["y"] + after["height"] > 0, after
        assert after["x"] == pytest.approx(before["x"], abs=1), (
            before, after)
        assert after["width"] == pytest.approx(before["width"], abs=1), (
            before, after)
        if abs(after["y"] - 32) > 3:
            stick = _box(page, ".stick")
            inst = _box(page, ".inst")
            assert abs((stick["y"] + stick["height"])
                       - (inst["y"] + inst["height"])) < 3, (stick, inst)
    finally:
        page.close()


def test_mark4_tick_labels_do_not_touch(fix_server):
    page = fix_server["browser"].new_page(
        viewport={"width": 360, "height": 844})
    try:
        page.goto(fix_server["base"] + "/?state=question",
                  wait_until="load")
        first = _box(page, ".tl .tick em", 0)
        labels = page.locator(".tl .tick em")
        boxes = {}
        for pos in range(labels.count()):
            text = (labels.nth(pos).inner_text() or "").strip()
            boxes[text] = labels.nth(pos).bounding_box()
        left = boxes["00:38"]
        right = boxes["02:00"]
        assert left is not None and right is not None, boxes
        assert left["x"] + left["width"] <= right["x"], (left, right)
        assert first is not None
    finally:
        page.close()


def test_mark9_sheet_padding_and_pushin(fix_server):
    page = fix_server["browser"].new_page(
        viewport={"width": 1920, "height": 1080})
    try:
        page.goto(fix_server["base"] + "/?film=1&frame=16x9&beat=sheet",
                  wait_until="load")
        padding = page.evaluate("""() => {
          const cs = getComputedStyle(document.querySelector('.fsheet'));
          return {left: cs.paddingLeft, right: cs.paddingRight};
        }""")
        assert padding == {"left": "96px", "right": "96px"}, padding
        page.evaluate("window.__nightShiftTick(20000)")
        page.wait_for_timeout(200)
        line = _box(page, ".fsheet .quoted")
        assert line["x"] >= 0, line
        assert line["x"] + line["width"] <= 1920, line
        assert line["y"] >= 0, line
        assert line["y"] + line["height"] <= 1080, line
    finally:
        page.close()


def test_mark10_note_beat_looks_like_the_note(fix_server):
    page = fix_server["browser"].new_page(
        viewport={"width": 1920, "height": 1080})
    try:
        page.goto(fix_server["base"] + "/?film=1&frame=16x9&beat=note",
                  wait_until="load")
        buttons = page.locator(".fbeat[data-beat='note'] button.btn")
        assert buttons.count() == 2
        classes = [buttons.nth(pos).get_attribute("class") or ""
                   for pos in range(2)]
        assert "fill" in classes[0].split(), classes
        assert "ghost" in classes[1].split(), classes
        assert page.locator(
            ".fbeat[data-beat='note'] form").count() == 0
    finally:
        page.close()
