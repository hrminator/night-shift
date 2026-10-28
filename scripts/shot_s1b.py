"""S1b screenshots: film beats at 1920x1080, the 9x16 note, morning after dawn.

Self-contained: seeds one live morning in a temp DATA_DIR, serves it on
port 8123, shoots twelve PNGs into docs/screens/s1b/, asserts zero
horizontal overflow at every width, and prints page weights.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
RECORDED = "6c7c7c742513"
BEATS = ["brief", "read", "verdict", "sheet", "diff", "checks", "decision",
         "note", "dawn", "morning"]


def main() -> None:
    from tests.test_s1a_accept import seed_live_morning
    tmp = Path(tempfile.mkdtemp(prefix="s1b-shots-"))
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["RECORDED_JOB"] = RECORDED
    record = json.loads(
        (ROOT / "data" / "runs" / f"job-{RECORDED}.json").read_text(
            encoding="utf-8"))
    morning_job = seed_live_morning(record)
    cues = json.loads((ROOT / "film" / "cues.json").read_text(
        encoding="utf-8"))
    cue_ms = {entry["name"]: int(entry["ms"]) for entry in cues["beats"]}
    env = dict(os.environ, UV_CACHE_DIR=str(ROOT / ".uv-cache"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env)
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
            raise SystemExit("server never came up on 8123")
        from playwright.sync_api import sync_playwright
        out = ROOT / "docs" / "screens" / "s1b"
        out.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1920,
                                                  "height": 1080})
                for beat in BEATS:
                    # Dawn sits mid-rise so the band shows; the rest hold
                    # their end-of-beat frame.
                    target = 4800 if beat == "dawn" else cue_ms[beat]
                    page.goto(BASE + f"/?film=1&frame=16x9&beat={beat}",
                              wait_until="load")
                    page.evaluate("document.fonts.ready.then(() => 1)")
                    page.evaluate(f"window.__nightShiftTick({target})")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth")
                    assert overflow <= 1920, (beat, overflow)
                    page.screenshot(
                        path=str(out / f"{beat}-1920x1080.png"),
                        full_page=False, animations="disabled")
                    print(f"shot {beat} 1920x1080 (scrollWidth {overflow})")
                page.set_viewport_size({"width": 1080, "height": 1920})
                page.goto(BASE + "/?film=1&frame=9x16&beat=note",
                          wait_until="load")
                page.evaluate("document.fonts.ready.then(() => 1)")
                page.evaluate(f"window.__nightShiftTick({cue_ms['note']})")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth")
                assert overflow <= 1080, ("note-9x16", overflow)
                page.screenshot(path=str(out / "note-1080x1920.png"),
                                full_page=False, animations="disabled")
                print(f"shot note 1080x1920 (scrollWidth {overflow})")
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(BASE + f"/jobs/{morning_job}/morning?dawn=1",
                          wait_until="load")
                page.wait_for_timeout(800)
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth")
                assert overflow <= 390, ("morning-dawn", overflow)
                page.screenshot(
                    path=str(out / "morning-dawn-390x844.png"),
                    full_page=False)
                print(f"shot morning-dawn 390x844 (scrollWidth {overflow})")
            finally:
                browser.close()
        css = (ROOT / "static" / "night.css").stat().st_size
        js = (ROOT / "static" / "night.js").stat().st_size
        weights = [("home-replay", "/"),
                   ("state-night", "/?state=night"),
                   ("state-question", "/?state=question"),
                   ("morning", f"/jobs/{morning_job}/morning"),
                   ("film-16x9", "/?film=1&frame=16x9"),
                   ("film-beat", "/?film=1&frame=16x9&beat=checks")]
        for name, url in weights:
            with urllib.request.urlopen(BASE + url, timeout=10) as resp:
                html_len = len(resp.read())
            print(f"weight {name}: html {html_len} + css {css} + js {js} "
                  f"= {html_len + css + js} bytes")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
