"""Night Shift pages: hello at / and the source-evidence page at /evidence."""

from __future__ import annotations

import html
import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

def bundled_runs_dir() -> Path:
    """Bundled records baked into the image under the repo's data/runs."""
    return Path(__file__).resolve().parent.parent / "data" / "runs"


def seed_bundled_runs(target: Path | None = None, source: Path | None = None) -> list[Path]:
    """Copy bundled read-sources-*.json records into the runtime DATA_DIR."""
    dest = target if target is not None else data_dir() / "runs"
    src = source if source is not None else bundled_runs_dir()
    if sorted(dest.glob("read-sources-*.json")):
        return []
    try:
        if src.resolve() == dest.resolve():
            return []
    except OSError:
        pass
    if not src.is_dir():
        return []
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for item in sorted(src.glob("read-sources-*.json")):
        out = dest / item.name
        if out.exists():
            continue
        shutil.copyfile(item, out)
        copied.append(out)
    return copied


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_bundled_runs()
    yield


app = FastAPI(title="Night Shift", lifespan=lifespan)

#: The source whose quote block carries the scan-styled-PDF label.
SCAN_SOURCE = "baltic_quote_Q-1187-B.pdf"


def data_dir() -> Path:
    """Local run data; the deployed app sets DATA_DIR=/data (the volume)."""
    return Path(os.environ.get("DATA_DIR", "data"))


def latest_record() -> dict | None:
    files = sorted((data_dir() / "runs").glob("read-sources-*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def render_evidence(record: dict) -> str:
    esc = html.escape
    model = esc(str(record.get("model_reported", "?")))
    run_at = esc(str(record.get("run_at_utc", "?")))
    effort = esc(str(record.get("effort", "?")))

    blocks = []
    for claim in record.get("claims", []):
        source = esc(str(claim.get("source", "?")))
        version = claim.get("version")
        file_id = claim.get("file_id")
        if version:
            origin = f"version {esc(str(version))}"
        elif file_id:
            origin = f"file id {esc(str(file_id))}"
        else:
            origin = "unversioned"
        quote = esc(str(claim.get("quote", "")))
        label = ""
        if claim.get("source") == SCAN_SOURCE:
            label = "<p>scan-styled PDF (image only, no text layer)</p>"
        blocks.append(
            f"<section><h2>{source}</h2>{label}"
            f"<p>Claim: {quote}</p>"
            f"<blockquote>{quote}</blockquote>"
            f"<p>Source: {source}, {origin}</p></section>"
        )

    calls = []
    for call in record.get("calls", []):
        calls.append(
            "<li>"
            f"{esc(str(call.get('name', '?')))}: "
            f"{esc(str(call.get('seconds', '?')))} s, "
            f"input {esc(str(call.get('input_tokens', '?')))}, "
            f"output {esc(str(call.get('output_tokens', '?')))}, "
            f"reasoning {esc(str(call.get('reasoning_tokens', '?')))} "
            f"(effort {esc(str(call.get('effort', effort)))}, "
            f"{esc(str(call.get('status', '?')))})"
            "</li>"
        )

    replay = record.get("replay_input_tokens", "?")
    first = record.get("first_call_input_tokens", "?")
    return (
        "<!doctype html><html><head><title>Night Shift: source evidence</title></head>"
        "<body>"
        f"<h1>Source evidence: a real muse-spark-1.3 result, {run_at}</h1>"
        f"<p>Model: {model} · effort: {effort}</p>"
        + "".join(blocks)
        + "<h2>Timings and token counts</h2><ul>"
        + "".join(calls)
        + "</ul>"
        f"<p>Replay turn billed {esc(str(replay))} input tokens "
        f"vs {esc(str(first))} on the first call</p>"
        '<p><a href="/">Back to Night Shift</a></p>'
        "</body></html>"
    )


@app.get("/", response_class=HTMLResponse)
def hello() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "<!doctype html><html><head><title>Night Shift</title></head>"
        f"<body><h1>Night Shift</h1><p>{now}</p>"
        '<p><a href="/evidence">Source evidence: a real muse-spark-1.3 result</a></p>'
        "</body></html>"
    )


@app.get("/evidence", response_class=HTMLResponse)
def evidence():
    record = latest_record()
    if record is None:
        return HTMLResponse(
            "<!doctype html><html><head><title>No evidence yet</title></head>"
            "<body><h1>No source evidence recorded yet</h1></body></html>",
            status_code=404,
        )
    return render_evidence(record)
