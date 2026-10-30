"""Part 6: S1a acceptance (Playwright against a live test server).

No horizontal scroll at 360/390/430 px; one clean column at 1440; the
question and both buttons inside the first 390x844 viewport in State B;
the approve flip end to end; HTML+CSS+JS under 100 KB.
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
from app import gateway, replay, runner

RECORDED = "6c7c7c742513"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

SEED_DRAFTS = [
    {"to": "Vestland Tekstil portal",
     "subject": "Confirm Hold H-2041, 100 tote bags",
     "purpose": "order",
     "body": ("Hello Vestland Tekstil,\n\nReferencing capacity Hold H-2041 "
              "(production run Fri Nov 6, van to Sjosalen Wed Nov 11 "
              "08:00-12:00): please confirm our order for 100 tote bags "
              "with logo, print file fjord-fern-logo-print.pdf, delivery "
              "to Sjosalen, window Wed Nov 11 08:00-12:00, total NOK 2800.\n\n"
              "Ordering contact: Kari Strandli, studio coordinator.\n\n"
              "Best regards, Kari Strandli")},
    {"to": "Sjosalen events desk",
     "subject": "Van Wed 08-12 to Sjosalen",
     "purpose": "venue_note",
     "body": ("Hello Sjosalen,\n\nFor our customer day Thu Nov 12: a "
              "Vestland Tekstil van (Hold H-2041) will deliver 100 tote "
              "bags to Sjosalen on Wed Nov 11 08:00-12:00.\n\nThank you "
              "for receiving it in that window.\n\nBest regards, "
              "Kari Strandli")},
    {"to": "Rannavere Print quotes desk",
     "subject": "Q-1187-B arrival query",
     "purpose": "baltic_note",
     "body": ("Hello Rannavere Print,\n\nThanks for revised Quote Q-1187-B "
              "(100 tote bags, goods leave the warehouse by 10 November, "
              "replacing Q-1187).\n\nWe are declining for now as we need "
              "a guaranteed arrival date. Could you confirm one?\n\nBest "
              "regards, Kari Strandli")},
]


def _call(name, args, call_id):
    return {"type": "function_call", "call_id": call_id, "name": name,
            "arguments": json.dumps(args)}


def seed_live_morning(record: dict) -> str:
    """One live copy of the recorded night, resumed by a stub (no model)."""
    from app.store import list_events
    options = next(e for e in record["events"]
                   if e["kind"] == "question")["payload"]["options"]
    job_id = replay.copy_job_for_visitor(record, options[0])
    aid = next(e for e in list_events(job_id)
               if e["kind"] == "owner_answer")["id"]
    calls = [_call("submit_hold", {
        "portal": "vestland_portal", "action": "capacity_hold",
        "product": "100 tote bags with logo", "quantity": 100,
        "print_file": gateway.studio_print_file(),
        "address": "Sjøsalen, Sjøgaten 5, 5003 Bergen",
        "delivery_window": "Wed Nov 11 08:00-12:00",
        "ordering_contact": gateway.studio_contact_text(),
        "recipient_can_receive": True,
        "cost": 0, "binding": False, "hold_ends": "09:00",
        "sources": {
            "recipient_can_receive": {"kind": "owner_answer", "id": aid},
            "route": {"kind": "portal", "version": 1},
            "window": {"kind": "portal", "version": 1},
            "ordering_contact": {"kind": "studio_file"},
            "print_file": {"kind": "studio_file"}}}, "s1")]
    calls += [_call("propose_message", draft, f"p{pos}")
              for pos, draft in enumerate(SEED_DRAFTS)]
    state = {"n": 0}

    def stub(instructions, input_items, **kwargs):
        n = state["n"]
        state["n"] += 1
        if n < len(calls):
            return {"output": [calls[n]], "text": ""}
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "night complete"}]}], "text": "x"}

    summary = runner.resume_job(job_id, respond_fn=stub)
    assert summary["status"] == "done", summary
    return job_id


@pytest.fixture(scope="module")
def live_server():
    """Uvicorn on 8123 over a seeded DATA_DIR, plus Playwright browser."""
    tmp = Path(tempfile.mkdtemp(prefix="s1a-accept-"))
    old_data = os.environ.get("DATA_DIR")
    old_rec = os.environ.get("RECORDED_JOB")
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["RECORDED_JOB"] = RECORDED
    record = json.loads(
        (Path("data/runs") / f"job-{RECORDED}.json").read_text(
            encoding="utf-8"))
    view_job = seed_live_morning(record)
    flip_job = seed_live_morning(record)
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
            yield {"base": BASE, "view": view_job, "flip": flip_job,
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


def _state_urls(server) -> list[str]:
    return ["/?state=night", "/?state=question",
            f"/jobs/{server['view']}/morning"]


def test_page_weight_under_100kb(live_server):
    css = (Path("static") / "night.css").read_bytes()
    js = (Path("static") / "night.js").read_bytes()
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    for url in _state_urls(live_server):
        html_bytes = client.get(url).content
        total = len(html_bytes) + len(css) + len(js)
        assert total < 100 * 1024, (url, total)


def test_no_horizontal_scroll_narrow(live_server):
    page = live_server["browser"].new_page()
    try:
        for width in (360, 390, 430):
            page.set_viewport_size({"width": width, "height": 844})
            for url in _state_urls(live_server):
                page.goto(live_server["base"] + url,
                          wait_until="load")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth")
                assert overflow <= width, (url, width, overflow)
    finally:
        page.close()


def test_one_clean_column_at_1440(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 1440, "height": 900})
    try:
        for url in _state_urls(live_server):
            page.goto(live_server["base"] + url, wait_until="load")
            assert page.evaluate(
                "document.documentElement.scrollWidth") <= 1440, url
            box = page.locator(".wrap").first.bounding_box()
            assert box is not None, url
            assert box["width"] <= 1200, (url, box["width"])
            left = box["x"]
            expect = (1440 - box["width"]) / 2
            assert abs(left - expect) < 4, (url, left, expect)
    finally:
        page.close()


def test_state_b_first_viewport_holds_question_and_buttons(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"] + "/?state=question",
                  wait_until="load")
        asked = page.locator(".note h2").first.bounding_box()
        assert asked is not None
        assert asked["y"] >= 0 and asked["y"] + asked["height"] <= 844, \
            asked
        buttons = page.locator(
            ".note form[action='/visitor/answer'] .btn")
        assert buttons.count() == 2
        for pos in range(2):
            box = buttons.nth(pos).bounding_box()
            assert box is not None
            assert box["y"] >= 0 and box["y"] + box["height"] <= 844, box
    finally:
        page.close()


def test_approve_flip_end_to_end(live_server):
    page = live_server["browser"].new_page(
        viewport={"width": 390, "height": 844})
    try:
        page.goto(live_server["base"]
                  + f"/jobs/{live_server['flip']}/morning",
                  wait_until="load")
        letter = page.locator(".letter[data-draft]").first
        approve = letter.locator("button[data-approve]")
        box = letter.locator("textarea.edit")
        original = box.input_value()
        assert approve.inner_text() == "Approve this exact text"
        box.fill(original + " One more sentence.")
        assert approve.inner_text() == "Your OK doesn't cover this version"
        assert approve.is_disabled()
        box.fill(original)
        assert approve.inner_text() == "Approve this exact text"
        assert not approve.is_disabled()
        approve.click()
        page.wait_for_load_state("load")
        assert "SIMULATED DELIVERY" in page.content()
        assert page.content().count("Approve this exact text") == 2
    finally:
        page.close()
