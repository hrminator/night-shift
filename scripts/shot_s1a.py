"""S1a screenshots: states A/B/C at 390x844 (full + fold) and 1440x900.

Self-contained: seeds one live morning in a temp DATA_DIR, serves it on
port 8123, shoots nine PNGs into docs/screens/s1a/, asserts zero
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


def main() -> None:
    from tests.test_s1a_accept import seed_live_morning
    tmp = Path(tempfile.mkdtemp(prefix="s1a-shots-"))
    os.environ["DATA_DIR"] = str(tmp)
    os.environ["RECORDED_JOB"] = RECORDED
    record = json.loads(
        (ROOT / "data" / "runs" / f"job-{RECORDED}.json").read_text(
            encoding="utf-8"))
    morning_job = seed_live_morning(record)
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
        out = ROOT / "docs" / "screens" / "s1a"
        out.mkdir(parents=True, exist_ok=True)
        shots = [
            ("night", "/?state=night"),
            ("question", "/?state=question"),
            ("morning", f"/jobs/{morning_job}/morning"),
        ]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390,
                                                  "height": 844})
                for name, url in shots:
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.goto(BASE + url, wait_until="load")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth")
                    assert overflow <= 390, (name, overflow)
                    page.screenshot(path=str(out / f"{name}-390x844.png"),
                                    full_page=True)
                    page.screenshot(
                        path=str(out / f"{name}-390x844-fold.png"),
                        full_page=False)
                    print(f"shot {name} 390x844 full+fold "
                          f"(scrollWidth {overflow})")
                page.set_viewport_size({"width": 1440, "height": 900})
                for name, url in shots:
                    page.goto(BASE + url, wait_until="load")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth")
                    assert overflow <= 1440, (name, overflow)
                    page.screenshot(path=str(out / f"{name}-1440x900.png"),
                                    full_page=True)
                    print(f"shot {name} 1440x900 (scrollWidth {overflow})")
            finally:
                browser.close()
        css = (ROOT / "static" / "night.css").stat().st_size
        js = (ROOT / "static" / "night.js").stat().st_size
        for name, url in shots:
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
