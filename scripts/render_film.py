"""S1b part 4: render film beats to PNG frames plus a WebM, deterministically.

Uses Playwright (the same Chromium the tests use) and the page's own
deterministic clock: every frame is a __nightShiftTick advance followed by a
screenshot, so two renders of the same beat are pixel-identical. Frames are
frame-exact PNG screenshots; the WebM is assembled from those frames with
system ffmpeg (libvpx-vp9), never a wall-clock screen recording.

Usage:
  uv run python scripts/render_film.py --beat dawn --frame 16x9
      --out docs/film/frames/dawn-16x9 --webm docs/film/dawn-5s.webm
      --seconds 5
  uv run python scripts/render_film.py --check-determinism --beat dawn
  uv run python scripts/render_film.py --beats sheet,checks,note,dawn
      --seconds-each 3 --out docs/film/gif-source --no-webm
  uv run python scripts/render_film.py --beats-png --out docs/film/beats
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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
RECORDED = "387faa63af38"
FPS = 30

VIEWPORTS = {"16x9": {"width": 1920, "height": 1080},
             "9x16": {"width": 1080, "height": 1920}}

#: Representative tick point per beat for docs/film/beats/ (ms into the beat;
#: "end" holds the final frame; dawn sits mid-rise so the band shows).
BEAT_STILLS = {"brief": "end", "read": "end", "verdict": "end",
               "sheet": "end", "diff": "end", "checks": "end",
               "decision": "end", "note": "end", "dawn": 4800,
               "morning": "end"}


def load_cues() -> dict:
    return json.loads((ROOT / "film" / "cues.json").read_text(
        encoding="utf-8"))


def beat_ms(name: str) -> int:
    for entry in load_cues()["beats"]:
        if entry["name"] == name:
            return int(entry["ms"])
    raise KeyError(f"unknown beat {name!r}")


def start_server(port: int = PORT) -> subprocess.Popen:
    """Uvicorn over a temp DATA_DIR; film reads the bundled export."""
    tmp = Path(tempfile.mkdtemp(prefix="render-film-"))
    env = dict(os.environ, DATA_DIR=str(tmp), RECORDED_JOB=RECORDED,
               UV_CACHE_DIR=str(ROOT / ".uv-cache"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/", timeout=5) as resp:
                if resp.status == 200:
                    return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"server never came up on {port} (kill stale uvicorn?)")


def wait_stable(page) -> None:
    """Same fonts and layout on every render, before frame 0."""
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.wait_for_function("document.fonts.status === 'loaded'")
    page.wait_for_timeout(300)


def film_url(frame: str, beat: str = "") -> str:
    url = f"{BASE}/?film=1&frame={frame}"
    return url + (f"&beat={beat}" if beat else "")


def render_url(browser, url: str, total_ms: int, fps: int, out_dir: Path,
               start_index: int = 0) -> int:
    """Tick through total_ms screenshotting at fps; returns frames written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    count = max(1, int(round(total_ms * fps / 1000)))
    page = browser.new_page()  # browser may be a _sized wrapper
    page.goto(url, wait_until="load")
    wait_stable(page)
    vnow = 0.0
    for pos in range(count):
        target = pos * 1000.0 / fps
        page.evaluate(f"window.__nightShiftTick({target - vnow!r})")
        vnow = target
        page.screenshot(path=str(out_dir / f"frame_{start_index + pos:05d}.png"),
                        animations="disabled")
    page.close()
    return count


def render_beat(browser, frame: str, beat: str, fps: int, out_dir: Path,
                seconds: float | None = None) -> int:
    """One beat (or its first `seconds`) to PNG frames."""
    total = beat_ms(beat)
    if seconds is not None:
        total = min(total, int(seconds * 1000))
    return render_url(browser, film_url(frame, beat), total, fps, out_dir)


def frames_identical(left: Path, right: Path) -> tuple[bool, str]:
    """True when two frame folders hold byte-identical PNGs in order."""
    a = sorted(left.glob("frame_*.png"))
    b = sorted(right.glob("frame_*.png"))
    if not a:
        return False, "no frames rendered"
    if [p.name for p in a] != [p.name for p in b]:
        return False, f"frame lists differ ({len(a)} vs {len(b)})"
    for x, y in zip(a, b):
        if x.read_bytes() != y.read_bytes():
            return False, f"first diff at {x.name}"
    return True, f"{len(a)} frames identical"


def check_determinism(browser, frame: str, beat: str, fps: int,
                      work: Path) -> tuple[bool, str]:
    """Render one beat twice; the determinism acceptance assertion."""
    first = work / "det-a"
    second = work / "det-b"
    render_beat(browser, frame, beat, fps, first)
    render_beat(browser, frame, beat, fps, second)
    return frames_identical(first, second)


def assemble_webm(frames_dir: Path, fps: int, out_path: Path) -> str:
    """Frame-exact PNG frames to WebM with system ffmpeg (vp9)."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", str(frames_dir / "frame_%05d.png"),
           "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p",
           "-crf", "32", "-b:v", "0", str(out_path)]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {done.stderr[-2000:]}")
    version = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                             text=True, timeout=30).stdout.splitlines()
    return version[0] if version else "ffmpeg"


def render_beats_png(browser, frame: str, out_dir: Path) -> list[Path]:
    """One representative PNG per beat (the committed stills)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, at in BEAT_STILLS.items():
        total = beat_ms(name)
        target = total if at == "end" else min(int(at), total)
        page = browser.new_page()
        page.goto(film_url(frame, name), wait_until="load")
        wait_stable(page)
        page.evaluate(f"window.__nightShiftTick({float(target)!r})")
        out = out_dir / f"{name}-{frame}.png"
        page.screenshot(path=str(out), animations="disabled")
        page.close()
        paths.append(out)
        print(f"still {name} at {target} ms -> {out.name}")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render film beats to PNG frames + WebM.")
    parser.add_argument("--frame", default="16x9",
                        choices=("16x9", "9x16"))
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--beat", default="")
    parser.add_argument("--beats", default="")
    parser.add_argument("--sequence", action="store_true")
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--seconds-each", type=float, default=None)
    parser.add_argument("--out", default="docs/film/frames/out")
    parser.add_argument("--webm", default="")
    parser.add_argument("--no-webm", action="store_true")
    parser.add_argument("--check-determinism", action="store_true")
    parser.add_argument("--beats-png", action="store_true")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)

    from playwright.sync_api import sync_playwright

    proc = start_server(args.port)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                viewport = VIEWPORTS[args.frame]
                if args.check_determinism:
                    if not args.beat:
                        raise SystemExit("--check-determinism needs --beat")
                    work = Path(tempfile.mkdtemp(prefix="render-det-"))
                    ok, detail = check_determinism(
                        _sized(browser, viewport), args.frame, args.beat,
                        args.fps, work)
                    print(f"determinism {args.beat}: "
                          f"{'PASS' if ok else 'FAIL'} ({detail})")
                    return 0 if ok else 1
                if args.beats_png:
                    render_beats_png(_sized(browser, viewport), args.frame,
                                     Path(args.out))
                    return 0
                out_dir = Path(args.out)
                if args.beat:
                    count = render_beat(_sized(browser, viewport),
                                        args.frame, args.beat, args.fps,
                                        out_dir, args.seconds)
                    print(f"rendered {count} frames -> {out_dir}")
                elif args.beats:
                    names = [n.strip() for n in args.beats.split(",")
                             if n.strip()]
                    index = 0
                    for name in names:
                        span = (args.seconds_each if args.seconds_each
                                else beat_ms(name) / 1000)
                        wrote = render_url(
                            _sized(browser, viewport),
                            film_url(args.frame, name),
                            min(beat_ms(name), int(span * 1000)),
                            args.fps, out_dir, start_index=index)
                        index += wrote
                    print(f"rendered {index} frames -> {out_dir}")
                elif args.sequence:
                    total = load_cues()["total_ms"]
                    if args.seconds is not None:
                        total = min(total, int(args.seconds * 1000))
                    count = render_url(_sized(browser, viewport),
                                       film_url(args.frame), total,
                                       args.fps, out_dir)
                    print(f"rendered {count} frames -> {out_dir}")
                else:
                    raise SystemExit("need --beat, --beats, --sequence, "
                                     "--beats-png or --check-determinism")
                if not args.no_webm:
                    webm = Path(args.webm) if args.webm else (
                        out_dir / "render.webm")
                    tag = assemble_webm(out_dir, args.fps, webm)
                    print(f"webm -> {webm} ({tag})")
            finally:
                browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


class _sized:
    """A browser wrapper that opens every page at the render viewport."""

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


if __name__ == "__main__":
    raise SystemExit(main())
