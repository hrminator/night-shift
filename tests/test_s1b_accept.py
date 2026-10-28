"""Part 5: S1b acceptance (Playwright against a live test server).

The replay reaches state B in 20-25 s at speed 1 with the same DOM text as
?state=question; skip works mid-replay; ?state=morning never runs the dawn;
reduced motion shows everything at once; no horizontal scroll at 360/390/430;
the film 16x9 frame keeps the lower third free; page weight under 100 KB;
the two shortest beats render pixel-identically twice.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

import app.main as main_mod
from scripts import render_film as render_mod
from tests.test_s1a_accept import seed_live_morning

RECORDED = "6c7c7c742513"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
BEATS = ["brief", "read", "verdict", "sheet", "diff", "checks", "decision",
         "note", "dawn", "morning"]


@pytest.fixture(scope="module")
def live_server():
    """Uvicorn on 8123 over a seeded DATA_DIR, plus Playwright browser."""
    tmp = Path(tempfile.mkdtemp(prefix="s1b-accept-"))
    old_data = os.environ.get("DATA_DIR")
    old_rec = os.environ.get("RECORDED_JOB")
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["RECORDED_JOB"] = RECORDED
    record = json.loads(
        (Path("data/runs") / f"job-{RECORDED}.json").read_text(
            encoding="utf-8"))
    morning_job = seed_live_morning(record)
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
                   "browser": browser}
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


def _tick_to_done(page, step: int = 500, limit: int = 30000) -> int:
    vnow, done = 0, False
    while vnow < limit and not done:
        out = page.evaluate(f"window.__nightShiftTick({step})")
        vnow, done = out["vnow"], out["done"]
    assert done, "replay never finished"
    return vnow


def test_replay_reaches_state_b_in_20_to_25_seconds(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"] + "/", wait_until="load")
        assert page.evaluate(
            "window.__nightShiftReplay.duration") == 20500
        vnow = _tick_to_done(page)
        assert 20000 <= vnow <= 25000, vnow
        assert page.evaluate(
            "document.body.getAttribute('data-replay-done')") == "1"
        assert page.evaluate("document.getElementById('replay')") is None
        assert page.locator(".note h2").is_visible()
    finally:
        page.close()


def test_finished_replay_matches_state_question_text(live_server):
    browser = live_server["browser"]
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"] + "/", wait_until="load")
        _tick_to_done(page)
        finished = " ".join(
            page.evaluate("document.body.innerText").split())
        page.goto(live_server["base"] + "/?state=question",
                  wait_until="load")
        static = " ".join(
            page.evaluate("document.body.innerText").split())
        assert finished == static
    finally:
        page.close()


def test_speed_scales_the_replay(live_server):
    browser = live_server["browser"]
    for speed, expect in (("2", 10250), ("4", 5250)):
        page = browser.new_page()
        try:
            page.goto(live_server["base"] + f"/?speed={speed}",
                      wait_until="load")
            assert _tick_to_done(page, step=250) == expect, speed
        finally:
            page.close()


def test_skip_works_from_the_2230_beat(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"] + "/", wait_until="load")
        page.evaluate("window.__nightShiftTick(3400)")
        assert "22:30" in page.locator(".clock").first.inner_text()
        page.locator(".skip a").click()
        page.wait_for_load_state("load")
        assert "state=question" in page.url, page.url
        assert page.locator(".note h2").is_visible()
    finally:
        page.close()


def test_state_morning_runs_no_dawn(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"] + "/?state=morning",
                  wait_until="load")
        assert "Good morning" in page.content()
        assert page.evaluate("document.getElementById('dawn')") is None
        assert "arrive-dawn" not in page.evaluate(
            "document.body.className")
    finally:
        page.close()


def test_reduced_motion_shows_everything_at_once(live_server):
    context = live_server["browser"].new_context(
        viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    try:
        page = context.new_page()
        page.goto(live_server["base"] + "/", wait_until="load")
        items = page.locator("#replay [data-rv]")
        count = items.count()
        assert count > 0
        for pos in range(count):
            assert items.nth(pos).is_visible(), pos
        assert page.evaluate(
            "document.getElementById('state-question').hidden") is False
    finally:
        context.close()


def test_no_horizontal_scroll_narrow(live_server):
    page = live_server["browser"].new_page()
    try:
        morning = f"/jobs/{live_server['morning']}/morning"
        for width in (360, 390, 430):
            page.set_viewport_size({"width": width, "height": 844})
            page.goto(live_server["base"] + "/", wait_until="load")
            page.evaluate("window.__nightShiftTick(5000)")
            overflow = page.evaluate(
                "document.documentElement.scrollWidth")
            assert overflow <= width, ("replay mid-flight", width, overflow)
            _tick_to_done(page)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth")
            assert overflow <= width, ("replay done", width, overflow)
            for url in ("/?state=question", morning):
                page.goto(live_server["base"] + url, wait_until="load")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth")
                assert overflow <= width, (url, width, overflow)
    finally:
        page.close()


def test_film_lower_third_stays_free(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 1920, "height": 1080})
    try:
        for beat in BEATS:
            page.goto(
                live_server["base"] + f"/?film=1&frame=16x9&beat={beat}",
                wait_until="load")
            total = page.evaluate("window.__nightShiftFilm.total")
            page.evaluate(f"window.__nightShiftTick({total})")
            boxes = page.evaluate(
                """Array.from(document.querySelectorAll(
                     '.fbeat.on .fc, .fbeat.on .fc *, .fclock, .fclock *'))
                   .filter(el => el.offsetParent !== null)
                   .map(el => el.getBoundingClientRect().bottom)""")
            assert boxes, beat
            assert max(boxes) <= 720, (beat, max(boxes))
    finally:
        page.close()


def test_page_weight_under_100kb(live_server):
    css = (Path("static") / "night.css").read_bytes()
    js = (Path("static") / "night.js").read_bytes()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    urls = ["/", "/?state=night", "/?state=question",
            f"/jobs/{live_server['morning']}/morning",
            "/?film=1&frame=16x9", "/?film=1&frame=16x9&beat=checks"]
    for url in urls:
        total = len(client.get(url).content) + len(css) + len(js)
        assert total < 100 * 1024, (url, total)


class _viewport_pages:
    """Adapter: render helpers opening pages at one viewport."""

    def __init__(self, browser, viewport: dict):
        self._browser = browser
        self._viewport = viewport

    def new_page(self, **kwargs):
        context = self._browser.new_context(viewport=self._viewport)
        page = context.new_page(**kwargs)
        raw_close = page.close

        def close(**close_kwargs):
            raw_close(**close_kwargs)
            context.close()

        page.close = close
        return page


def test_shortest_beats_render_identically_twice(live_server, tmp_path):
    cues = render_mod.load_cues()
    shortest = sorted(cues["beats"], key=lambda b: b["ms"])[:2]
    assert [b["name"] for b in shortest] == ["diff", "morning"]
    pages = _viewport_pages(live_server["browser"],
                            {"width": 1920, "height": 1080})
    for entry in shortest:
        first = tmp_path / f"{entry['name']}-a"
        second = tmp_path / f"{entry['name']}-b"
        render_mod.render_beat(pages, "16x9", entry["name"], 5, first)
        render_mod.render_beat(pages, "16x9", entry["name"], 5, second)
        ok, detail = render_mod.frames_identical(first, second)
        assert ok, (entry["name"], detail)
