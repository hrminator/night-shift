"""Night Shift pages: hello at /, source evidence, and plain job pages."""

from __future__ import annotations

import html
import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
        '<form method="post" action="/jobs/run">'
        '<button type="submit">Start a night job (runs one decision turn)</button>'
        "</form>"
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


def _decision_section(events: list) -> str:
    esc = html.escape
    checks = [e for e in events if e["kind"] == "check"]
    decisions = [e for e in events if e["kind"] == "decision"]
    claims = {e["id"]: e for e in events if e["kind"] == "claim"}
    if not checks and not decisions:
        return ""
    items = "".join(f"<li>{esc(str((c['payload'] or {}).get('name', '?')))}: {esc(str((c['payload'] or {}).get('result', '?')))} — {esc(str((c['payload'] or {}).get('note', '')))}</li>" for c in checks)
    blocks = ""
    for d in decisions:
        p = d["payload"] or {}
        cites = "".join(f"<blockquote>{esc(str(claims[cid]['payload'].get('quote', '')))} <cite>({esc(str(claims[cid]['payload'].get('source', '')))})</cite></blockquote>" for cid in (p.get("evidence") or []) if cid in claims)
        blocks += f"<p>Decision: {esc(str(p.get('outcome', '?')))} — {esc(str(p.get('reason', '')))} (evidence {esc(str(p.get('evidence', '')))})</p>{cites}"
    return f"<section><h2>How it decided</h2><ul>{items}</ul>{blocks}</section>"

def _summarize(kind: str, payload: dict) -> str:
    if kind == "handoff":
        return "Owner hands over the brief at 21:30 and goes offline."
    if kind == "revised_quote":
        return (
            f"{payload.get('quote', '?')} arrived; replaces {payload.get('replaces', '?')}."
        )
    if kind == "claim":
        quote = str(payload.get("quote", ""))[:160]
        return f"{payload.get('source', '?')}: {quote}"
    if kind == "decision":
        return f"{payload.get('outcome', '?')}: {str(payload.get('reason', ''))[:200]}"
    if kind == "question":
        return str(payload.get("question", ""))[:200]
    if kind == "checkpoint":
        return "Saved point for resume (full next-call input stored)."
    if kind == "owner_answer":
        return f"Owner answered: {payload.get('choice', '?')} (source: owner)."
    if kind == "check":
        return f"check {payload.get('name', '?')}: {payload.get('result', '?')} — {str(payload.get('note', ''))[:200]}"
    if kind == "gateway_check":
        mark = "pass" if payload.get("passed") else "FAIL"
        return f"gateway {payload.get('check', '?')}: {mark}"
    if kind == "permission_used":
        return f"permission from brief {payload.get('brief_version', '?')}"
    if kind == "gateway_result":
        return f"gateway {payload.get('tool', '?')}: ok={payload.get('ok')}"
    if kind == "effect":
        return f"effect {payload.get('hold_id', '?')}: {payload.get('acknowledgement', '')[:120]}"
    if kind == "draft":
        return f"draft to {payload.get('to', '?')}: {str(payload.get('body', ''))[:120]}"
    if kind == "turn_done":
        return f"turn done after {payload.get('tool_calls', '?')} tool calls"
    if kind == "approval_requested":
        return f"approval requested for draft {payload.get('draft_id', '?')}"
    if kind == "resume_pruned_files":
        return f"resume pruned {payload.get('pruned_input_files', '?')} file items"
    if kind in ("tool_refused", "tool_malformed", "tool_limit"):
        return f"{kind}: {payload.get('error', payload.get('tool', ''))}"
    if kind == "model_plain_text":
        return "Model answered in plain text; nudged once."
    if kind == "step_failed":
        return f"Step failed: {payload.get('reason', '')}"
    return kind


@app.post("/jobs/run")
def run_job_route(variant: str = "hero"):
    from app import runner as runner_mod

    summary = runner_mod.run_job(variant=variant)
    return RedirectResponse(url=f"/jobs/{summary['job_id']}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    esc = html.escape
    events = store_mod.list_events(job_id)
    rows = "".join(
        f"<li><b>{esc(str(e['kind']))}</b> @{esc(str(e['virtual_time']))}"
        f" — {esc(_summarize(e['kind'], e['payload'] or {}))}</li>"
        for e in events
    )
    question = next(
        (e for e in reversed(events) if e["kind"] == "question"), None
    )
    card = ""
    if job.get("status") == "waiting_for_owner" and question is not None:
        payload = question["payload"] or {}
        options = payload.get("options") or []
        buttons = "".join(
            f'<button type="submit" name="choice" value="{esc(str(o))}">'
            f"{esc(str(o))}</button>"
            for o in options
        )
        card = (
            "<section><h2>Question for the owner</h2>"
            f"<p><b>{esc(str(payload.get('question', '')))}</b></p>"
            f"<p>Why now: {esc(str(payload.get('why_now', '')))}</p>"
            f"<p>Checked: {esc(str(payload.get('what_checked', '')))}</p>"
            f"<p>If yes: {esc(str(payload.get('if_yes', '')))}</p>"
            f"<p>If no: {esc(str(payload.get('if_no', '')))}</p>"
            f'<form method="post" action="/jobs/{esc(job_id)}/answer">'
            f"{buttons}</form></section>"
        )
    extra = ""
    if job.get("status") == "answered":
        extra = (
            "<section><h2>Answer recorded</h2>"
            f'<form method="post" action="/jobs/{esc(job_id)}/resume">'
            "<button type=\"submit\">Resume the night from the saved point"
            "</button></form></section>"
        )
    if job.get("status") == "done":
        extra = (
            "<section><h2>Night complete</h2>"
            f'<p><a href="/jobs/{esc(job_id)}/morning">Morning page</a></p>'
            "</section>"
        )
    return (
        "<!doctype html><html><head><title>Night Shift job</title></head><body>"
        f"<h1>Job {esc(job_id)}</h1>"
        f"{extra}"
        f"<p>Status: {esc(str(job.get('status', '?')))} · "
        f"clock: {esc(str(job.get('virtual_time', '?')))} · "
        f"step: {esc(str(job.get('current_step', '')))}</p>"
        f"{card}{_decision_section(events)}<h2>Events in order</h2><ol>{rows}</ol>"
        '<p><a href="/">Back to Night Shift</a></p></body></html>'
    )


@app.post("/jobs/{job_id}/answer")
async def job_answer(job_id: str, request: Request):
    import urllib.parse

    from app import runner as runner_mod
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    body = (await request.body()).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(body)
    choice = form.get("choice", [""])[0]
    virtual_time = form.get("virtual_time", ["01:05"])[0] or "01:05"
    runner_mod.store_answer(job_id, choice, virtual_time)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}/morning", response_class=HTMLResponse)
def morning_page(job_id: str):
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    esc = html.escape
    events = store_mod.list_events(job_id)
    effects = [e for e in events if e["kind"] == "effect"]
    drafts = [e for e in events if e["kind"] == "draft"]
    checks = [e for e in events if e["kind"] == "gateway_check"]
    if effects:
        label = (
            "Vestland slot held until 09:00 · Done: comparison, hold, "
            "3 drafts · Needs you: 3 approvals (the Vestland order before "
            "09:00) · Couldn't verify: Baltic's arrival · Supplier system "
            "and mail simulated"
        )
    else:
        label = (
            "No hold was placed · Done: comparison, drafts · "
            "Needs you: review · Couldn't verify: Baltic's arrival · "
            "Supplier system and mail simulated"
        )
    ack = ""
    for effect in effects:
        payload = effect["payload"] or {}
        ack += (
            "<section><h2>Hold acknowledgement</h2>"
            f"<p>{esc(str(payload.get('acknowledgement', '')))}</p></section>"
        )
    cards = ""
    for draft in drafts:
        payload = draft["payload"] or {}
        cards += (
            "<section><h3>"
            f"{esc(str(payload.get('purpose', 'message')))} · "
            f"{esc(str(payload.get('status', '')))}</h3>"
            f"<p>To: {esc(str(payload.get('to', '')))}</p>"
            f"<p>Subject: {esc(str(payload.get('subject', '')))}</p>"
            f"<blockquote>{esc(str(payload.get('body', '')))}</blockquote>{'<p><b>Not sent: recipient not in your contacts</b></p>' if payload.get('leak') else ''}"
            f'<form method="post" action="/jobs/{esc(job_id)}/approve">'
            f'<input type="hidden" name="draft_id" value="{draft["id"]}">'
            "<button type=\"submit\">Approve this exact text</button>"
            "</form></section>"
        )
    check_rows = "".join(
        "<li>"
        f"{esc(str((c['payload'] or {}).get('check', '?')))}: "
        f"{'pass' if (c['payload'] or {}).get('passed') else 'FAIL'} — "
        f"{esc(str((c['payload'] or {}).get('detail', '')))}"
        "</li>"
        for c in checks
    )
    return (
        "<!doctype html><html><head><title>Night Shift morning</title></head>"
        "<body>"
        f"<h1>Morning page · 07:00 virtual time · Job {esc(job_id)}</h1>"
        f"<p><b>{esc(label)}</b></p>"
        f"{ack}"
        f"<h2>Drafts awaiting your OK on the exact text</h2>{cards}"
        f"<h2>How it decided (gateway checks)</h2><ol>{check_rows}</ol>"
        '<p><a href="/">Back to Night Shift</a></p></body></html>'
    )


@app.post("/jobs/{job_id}/approve")
async def job_approve(job_id: str, request: Request):
    import urllib.parse

    from app import store as store_mod

    if store_mod.get_job(job_id) is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    body = (await request.body()).decode("utf-8", "replace")
    draft_id = urllib.parse.parse_qs(body).get("draft_id", [""])[0]
    store_mod.append_event(
        job_id, "07:00", "approval_requested", {"draft_id": draft_id},
    )
    return RedirectResponse(url=f"/jobs/{job_id}/morning", status_code=303)


@app.post("/jobs/{job_id}/resume")
def job_resume(job_id: str):
    from app import runner as runner_mod
    from app import store as store_mod

    if store_mod.get_job(job_id) is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    summary = runner_mod.resume_job(job_id)
    if summary["status"] == "refused":
        return HTMLResponse(
            f"<h1>Cannot resume</h1><p>{html.escape(str(summary['reason']))}</p>",
            status_code=400,
        )
    return RedirectResponse(url=f"/jobs/{job_id}/morning", status_code=303)
