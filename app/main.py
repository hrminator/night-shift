"""Night Shift pages: hello at /, source evidence, and plain job pages."""

from __future__ import annotations

import html
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

def bundled_runs_dir() -> Path:
    """Bundled records baked into the image under the repo's data/runs."""
    return Path(__file__).resolve().parent.parent / "data" / "runs"


def seed_bundled_runs(target: Path | None = None, source: Path | None = None) -> list[Path]:
    """Copy bundled run records into the runtime DATA_DIR.

    Copies every file under the bundled data/runs that does not already
    exist in DATA_DIR/runs. Existing files are never overwritten, so live
    exports on the volume always win over the baked-in copies.
    """
    dest = target if target is not None else data_dir() / "runs"
    src = source if source is not None else bundled_runs_dir()
    try:
        if src.resolve() == dest.resolve():
            return []
    except OSError:
        pass
    if not src.is_dir():
        return []
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for item in sorted(src.glob("*")):
        if not item.is_file():
            continue
        out = dest / item.name
        if out.exists():
            continue
        shutil.copyfile(item, out)
        copied.append(out)
    return copied


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_bundled_runs()
    if os.environ.get("NIGHT_SHIFT_AUTO_RESUME") == "1":
        try:
            from app import runner as _runner
            _runner.resume_open_jobs()
        except Exception as exc:  # noqa: BLE001 - startup must not fail
            print(f"startup resume skipped: {exc}", flush=True)
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


#: Where the front door points for the written results.
RESULTS_URL = "https://github.com/hrminator/night-shift#results"

#: Test seam: visitor resumes call this instead of the real adapter.
LIVE_RESPOND_FN = None

#: Minimal styling for the one product screen (plain HTML, no JS).
FRONT_CSS = (
    "<style>body{font-family:system-ui,-apple-system,sans-serif;"
    "max-width:46em;margin:2em auto;padding:0 1em;line-height:1.5}"
    "blockquote{border-left:3px solid #888;margin:.4em 0;padding:.1em .8em}"
    "li{margin:.45em 0}button{font-size:1em;margin:.2em;padding:.45em .9em}"
    ".label{background:#f0f0f0;padding:.6em .8em}</style>"
)


def _live_respond_fn():
    if LIVE_RESPOND_FN is not None:
        return LIVE_RESPOND_FN
    from app.adapter import respond
    return respond


def _spend_wrapping_respond(job_id: str, day: str):
    """Record every visitor-resume model call in the spend ledger."""
    inner = _live_respond_fn()

    def wrapped(instructions, input_items, **kwargs):
        result = inner(instructions, input_items, **kwargs)
        try:
            from app.spend import cost_usd, usage_of
            from app.store import record_spend
            inputs, cached, outputs = usage_of(result)
            record_spend(day, job_id, "visitor-resume", inputs, cached,
                         outputs, cost_usd(inputs, cached, outputs))
        except Exception:  # noqa: BLE001 - the ledger must not break a night
            pass
        return result

    return wrapped


def _replay_timeline(events: list) -> str:
    """Timeline from 21:30 to the question, from the exported events."""
    esc = html.escape
    claims = {e["id"]: e for e in events if e.get("kind") == "claim"}
    parts = []
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload") or {}
        vt = esc(str(event.get("virtual_time", "?")))
        if kind == "handoff":
            parts.append(
                f"<li><b>{vt}</b> — The owner hands over the brief "
                "and goes to bed.</li>"
            )
        elif kind == "claim":
            source = esc(str(payload.get("source", "?")))
            quote = esc(str(payload.get("quote", "")))
            meaning = esc(str(payload.get("claim", "")))
            parts.append(
                f"<li><b>{vt}</b> — Read <b>{source}</b>: "
                f"<blockquote>{quote}</blockquote><p>{meaning}</p></li>"
            )
        elif kind == "revised_quote":
            parts.append(
                f"<li><b>{vt} — the one scheduled event:</b> Baltic's "
                f"revised quote {esc(str(payload.get('quote', '?')))} "
                f"arrives and replaces "
                f"{esc(str(payload.get('replaces', '?')))}.</li>"
            )
        elif kind == "check":
            mark = "pass" if payload.get("result") == "pass" else "FAIL"
            parts.append(
                f"<li><b>{vt}</b> — check "
                f"{esc(str(payload.get('name', '?')))}: <b>{mark}</b> — "
                f"{esc(str(payload.get('note', '')))}</li>"
            )
        elif kind == "decision":
            cites = "".join(
                f"<blockquote>{esc(str(claims[cid]['payload'].get('quote', '')))}"
                f" <cite>({esc(str(claims[cid]['payload'].get('source', '')))})"
                "</cite></blockquote>"
                for cid in (payload.get("evidence") or [])
                if cid in claims
            )
            parts.append(
                f"<li><b>{vt}</b> — Decision: "
                f"{esc(str(payload.get('outcome', '?')))} — "
                f"{esc(str(payload.get('reason', '')))}"
                f" (evidence {esc(str(payload.get('evidence', '')))})</li>"
                f"{cites}"
            )
        elif kind == "checkpoint":
            parts.append(
                f"<li><b>{vt}</b> — Saved point. The night pauses here; "
                "nothing is ordered, nothing is sent.</li>"
            )
    return "<ol>" + "".join(parts) + "</ol>"


def _visitor_question_card(question: dict) -> str:
    """The recorded question with live answer buttons."""
    esc = html.escape
    payload = question.get("payload") or {}
    options = payload.get("options") or []
    buttons = "".join(
        f'<button type="submit" name="choice" value="{esc(str(o))}">'
        f"{esc(str(o))}</button>"
        for o in options
    )
    return (
        "<section><h2>You're the owner</h2>"
        "<p>Tap an answer. It starts a <b>new</b> live job from the saved "
        "point below (real model calls, its own outbox) and moves to that "
        "job's morning page. The recording is never changed.</p>"
        f"<p><b>{esc(str(payload.get('question', '')))}</b></p>"
        f"<p>Why now: {esc(str(payload.get('why_now', '')))}</p>"
        f"<p>Checked: {esc(str(payload.get('what_checked', '')))}</p>"
        f"<p>If yes: {esc(str(payload.get('if_yes', '')))}</p>"
        f"<p>If no: {esc(str(payload.get('if_no', '')))}</p>"
        f'<form method="post" action="/visitor/answer">{buttons}</form>'
        "</section>"
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """The one product screen: replay of the recorded hero run."""
    from app import replay as replay_mod

    resolved = replay_mod.resolve_recorded_job()
    if resolved is None:
        return (
            "<!doctype html><html><head><title>Night Shift</title></head>"
            f"<body>{FRONT_CSS}<h1>Night Shift</h1>"
            "<p>No recorded run yet.</p></body></html>"
        )
    record = resolved["record"]
    events = replay_mod.replay_events(record)
    question = next(
        (e for e in reversed(events) if e.get("kind") == "question"), None
    )
    card = _visitor_question_card(question) if question is not None else ""
    return (
        "<!doctype html><html><head><title>Night Shift</title></head>"
        f"<body>{FRONT_CSS}<h1>Night Shift</h1>"
        f"<p class=\"label\">Real muse-spark-1.3 calls recorded on "
        f"{html.escape(resolved['date'])}. Supplier system and mail "
        "simulated.</p>"
        f"<h2>Overnight replay: one job, 21:30 to the question</h2>"
        f"{_replay_timeline(events)}"
        f"{card}"
        f"{_decision_section(events)}"
        f"<p><a href=\"{RESULTS_URL}\">Results in the README</a> · "
        '<a href="/evidence">Source evidence: a real muse-spark-1.3 '
        "result</a></p>"
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
    if kind == "portal_error":
        return f"portal error: {payload.get('error', '?')}"
    if kind == "approval_requested":
        return f"approval requested for draft {payload.get('draft_id', '?')}"
    if kind == "resume_pruned_files":
        return f"resume pruned {payload.get('pruned_input_files', '?')} file items"
    if kind == "nudge":
        return f"nudge ({payload.get('rule', '?')}): {str(payload.get('message', ''))[:120]}"
    if kind == "approval":
        return f"approval for draft {payload.get('draft_id', '?')} at {payload.get('approved_at', '?')}"
    if kind == "delivered":
        return f"delivered to {payload.get('to', '?')}: {payload.get('outbox', '')}"
    if kind == "tool_name_normalised":
        return f"tool renamed {payload.get('requested', '?')} -> {payload.get('normalised', '?')}"
    if kind in ("tool_refused", "tool_malformed", "tool_limit"):
        return f"{kind}: {payload.get('error', payload.get('tool', ''))}"
    if kind == "model_plain_text":
        return "Model answered in plain text; nudged once."
    if kind == "step_failed":
        return f"Step failed: {payload.get('reason', '')}"
    return kind


@app.post("/jobs/run")
def run_job_route(request: Request, variant: str = "hero"):
    """Start a whole new night. Needs the X-Run-Token header, else 403."""
    expected = os.environ.get("RUN_TOKEN", "")
    token = request.headers.get("x-run-token", "")
    if not expected or token != expected:
        return HTMLResponse(
            "<h1>Forbidden</h1>"
            "<p>Starting a night needs the X-Run-Token header.</p>",
            status_code=403,
        )
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


def _draft_head_events(events: list) -> list:
    """One head event per draft key (latest version only)."""
    from app import gateway as gateway_mod
    heads: dict = {}
    for event in events:
        if event["kind"] != "draft":
            continue
        key = gateway_mod.draft_key_of(event)
        if key not in heads or event["id"] > heads[key]["id"]:
            heads[key] = event
    return [heads[key] for key in sorted(heads)]


def _draft_state(job_id: str, draft: dict, at_virtual: str = "07:00") -> str:
    """Approval state of one draft head: approved / needs approval again."""
    from app import gateway as gateway_mod
    key = gateway_mod.draft_key_of(draft)
    approvals = gateway_mod.approvals_for_key(job_id, key)
    if not approvals:
        return "awaiting approval"
    for approval in approvals:
        valid, _ = gateway_mod.approval_valid_at(job_id, approval["id"],
                                                 at_virtual)
        if valid and approval["payload"].get("draft_id") == draft["id"]:
            return "approved"
    return "needs approval again"


def _draft_cards(job_id: str, events: list, with_forms: bool = True) -> str:
    """Morning draft cards: head versions with approve + one-word-edit forms.

    Recorded pages render read-only (no live job to approve against)."""
    from app import gateway as gateway_mod
    esc = html.escape
    cards = ""
    earlier = ""
    _smap = gateway_mod.superseded_map_for(events)
    for draft in [d for d in _draft_head_events(events) if d["id"] not in _smap]:
        payload = draft["payload"] or {}
        version_hash = gateway_mod.head_version_hash(draft)
        state = _draft_state(job_id, draft)
        version = payload.get("version", 1)
        forms = ""
        if with_forms:
            forms = (
                f'<form method="post" action="/jobs/{esc(job_id)}/approve">'
                f'<input type="hidden" name="draft_id" value="{draft["id"]}">'
                f'<input type="hidden" name="version_hash" '
                f'value="{version_hash}">'
                '<input type="hidden" name="virtual_time" value="07:00">'
                "<button type=\"submit\">Approve this exact text</button>"
                "</form>"
                f'<form method="post" action="/jobs/{esc(job_id)}/edit-draft">'
                f'<input type="hidden" name="draft_id" value="{draft["id"]}">'
                "<textarea name=\"body\" rows=\"3\" cols=\"60\">"
                f"{esc(str(payload.get('body', '')))}</textarea>"
                "<button type=\"submit\">Save edited version</button>"
                "</form>"
            )
        leak = ("<p><b>Not sent: recipient not in your contacts</b></p>"
                if payload.get("leak") else "")
        cards += (
            "<section><h3>"
            f"{esc(str(payload.get('purpose', 'message')))} · {esc(state)}"
            f" · v{esc(str(version))}</h3>"
            f"<p>To: {esc(str(payload.get('to', '')))}</p>"
            f"<p>Subject: {esc(str(payload.get('subject', '')))}</p>"
            f"<blockquote>{esc(str(payload.get('body', '')))}</blockquote>"
            f"{leak}{forms}</section>"
        )
    for draft in [d for d in _draft_head_events(events) if d["id"] in _smap]:
        payload = draft["payload"] or {}
        version = payload.get("version", 1)
        mark = _smap[draft["id"]]
        earlier += (
            "<section><h3>"
            f"{esc(str(payload.get('purpose', 'message')))} · {mark}"
            f" · v{esc(str(version))}</h3>"
            f"<p>To: {esc(str(payload.get('to', '')))}</p>"
            f"<p>Subject: {esc(str(payload.get('subject', '')))}</p>"
            f"<blockquote>{esc(str(payload.get('body', '')))}</blockquote>"
            "</section>"
        )
    if earlier:
        cards += "<details><summary>Earlier versions (superseded drafts proposed before the 00:38 event)</summary>" + earlier + "</details>"
    return cards


def _outbox_section(events: list) -> str:
    """Simulated outbox: approved drafts moved here as delivered events."""
    esc = html.escape
    delivered = [e for e in events if e["kind"] == "delivered"]
    if not delivered:
        return "<p>Outbox empty.</p>"
    rows = "".join(
        "<li>"
        f"To {esc(str((d['payload'] or {}).get('to', '?')))}: "
        f"{esc(str((d['payload'] or {}).get('subject', '')))} — "
        f"{esc(str((d['payload'] or {}).get('outbox', '')))}"
        "</li>"
        for d in delivered
    )
    return f"<ul>{rows}</ul>"


def render_morning_page(job_title: str, events: list, banner: str = "",
                        job_id: str | None = None) -> str:
    """Morning page HTML for live jobs and recorded runs alike."""
    esc = html.escape
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
    cards = _draft_cards(job_id if job_id is not None else job_title,
                         events, with_forms=job_id is not None)
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
        f"<h1>Morning page · 07:00 virtual time · {esc(job_title)}</h1>"
        f"{banner}"
        f"<p><b>{esc(label)}</b></p>"
        f"{ack}"
        f"<h2>Drafts awaiting your OK on the exact text</h2>{cards}"
        f"<h2>Outbox (Simulated delivery)</h2>{_outbox_section(events)}"
        f"<h2>How it decided (gateway checks)</h2><ol>{check_rows}</ol>"
        '<p><a href="/">Back to Night Shift</a></p></body></html>'
    )


@app.get("/jobs/{job_id}/morning", response_class=HTMLResponse)
def morning_page(job_id: str):
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    return render_morning_page(f"Job {job_id}",
                               store_mod.list_events(job_id), job_id=job_id)


@app.post("/jobs/{job_id}/approve")
async def job_approve(job_id: str, request: Request):
    import urllib.parse

    from app import store as store_mod

    if store_mod.get_job(job_id) is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    body = (await request.body()).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(body)
    try:
        draft_id = int(form.get("draft_id", [""])[0])
    except ValueError:
        return HTMLResponse("<h1>Unknown draft</h1>", status_code=400)
    version_hash = form.get("version_hash", [""])[0]
    virtual_time = form.get("virtual_time", ["07:00"])[0] or "07:00"
    from app import gateway as gateway_mod
    approved = gateway_mod.approve_draft(job_id, draft_id, version_hash,
                                         virtual_time)
    if not approved.get("ok"):
        return HTMLResponse(
            "<h1>Approval refused</h1>"
            f"<p>{html.escape(str(approved.get('reason', '')))}</p>",
            status_code=400,
        )
    gateway_mod.deliver_approved(job_id, approved["approval_id"], virtual_time)
    return RedirectResponse(url=f"/jobs/{job_id}/morning", status_code=303)


@app.post("/jobs/{job_id}/edit-draft")
async def job_edit_draft(job_id: str, request: Request):
    import urllib.parse

    from app import store as store_mod

    if store_mod.get_job(job_id) is None:
        return HTMLResponse("<h1>Unknown job</h1>", status_code=404)
    body = (await request.body()).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(body)
    try:
        draft_id = int(form.get("draft_id", [""])[0])
    except ValueError:
        return HTMLResponse("<h1>Unknown draft</h1>", status_code=400)
    new_body = form.get("body", [""])[0]
    virtual_time = form.get("virtual_time", ["07:00"])[0] or "07:00"
    from app import gateway as gateway_mod
    edited = gateway_mod.edit_draft(job_id, draft_id, new_body, virtual_time)
    if not edited.get("ok"):
        return HTMLResponse(
            "<h1>Edit refused</h1>"
            f"<p>{html.escape(str(edited.get('reason', '')))}</p>",
            status_code=400,
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


def _recorded_morning(note: str):
    """Serve the recorded morning page with a one-line guard notice."""
    from app import replay as replay_mod

    resolved = replay_mod.resolve_recorded_job()
    if resolved is None:
        return HTMLResponse("<h1>No recorded run yet</h1>", status_code=404)
    banner = f"<p><b>{html.escape(note)}</b></p>"
    return render_morning_page(
        f"Recorded run {resolved['job_id']}",
        list(resolved["record"].get("events") or []), banner)


@app.post("/visitor/answer")
async def visitor_answer(request: Request):
    """Answer as the owner: copy the recorded run and resume it live."""
    import urllib.parse
    import uuid

    from app import replay as replay_mod
    from app import runner as runner_mod
    from app import spend as spend_mod
    from app import store as store_mod

    resolved = replay_mod.resolve_recorded_job()
    if resolved is None:
        return HTMLResponse("<h1>No recorded run yet</h1>", status_code=404)
    body = (await request.body()).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(body)
    choice = form.get("choice", [""])[0]
    if not choice:
        return HTMLResponse("<h1>Pick one of the two answers</h1>",
                            status_code=400)
    total, cap = spend_mod.spend_status()
    if total >= cap:
        return _recorded_morning(
            f"Live resume unavailable (daily spend cap of ${cap:.2f} "
            "reached; showing the recorded morning page).")
    owner = uuid.uuid4().hex[:12]
    slot = spend_mod.acquire_visitor_slot(owner)
    if slot is None:
        return _recorded_morning(
            "Live resume unavailable (2 live resumes already running; "
            "showing the recorded morning page).")
    try:
        try:
            new_id = replay_mod.copy_job_for_visitor(
                resolved["record"], choice)
        except ValueError as exc:
            return HTMLResponse(f"<h1>Cannot resume</h1><p>{exc}</p>",
                                status_code=400)
        run_lock = f"job:{new_id}:run"
        if not store_mod.acquire_lock(run_lock, owner, ttl_seconds=900):
            return _recorded_morning(
                "Live resume unavailable (2 live resumes already running; "
                "showing the recorded morning page).")
        try:
            runner_mod.resume_job(
                new_id,
                respond_fn=_spend_wrapping_respond(new_id,
                                                 spend_mod.today_utc()))
        finally:
            store_mod.release_lock(run_lock, owner)
    finally:
        spend_mod.release_visitor_slot(slot, owner)
    return RedirectResponse(url=f"/jobs/{new_id}/morning", status_code=303)
