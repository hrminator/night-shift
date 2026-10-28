"""Night Shift pages: hello at /, source evidence, and plain job pages."""

from __future__ import annotations

import base64
import html
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

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

#: Static assets (the owner-phone service worker). Shipped with the code.
app.mount("/static", StaticFiles(directory=str(
    Path(__file__).resolve().parent.parent / "static")), name="static")

#: Static design comps (S0): public, nothing secret, no auth.
app.mount("/comps", StaticFiles(directory=str(
    Path(__file__).resolve().parent.parent / "comps")), name="comps")

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


#: Display alias for evidence checks: stored events keep the old name
#: (existing jobs, including the recorded hero job, are never rewritten),
#: while pages show the new name for both old and new events.
CHECK_DISPLAY_NAMES = {"can_ask_now": "can_ask_supplier_or_venue_now"}


def display_check_name(name: object) -> str:
    """Name shown on pages for one evidence check."""
    return CHECK_DISPLAY_NAMES.get(str(name), str(name))


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


def recorded_costs_path() -> Path:
    """Measured cost file shipped with the code (job id -> tokens)."""
    return Path(__file__).resolve().parent.parent / "data" / "recorded_costs.json"


def recorded_cost_for(job_id: str) -> dict | None:
    """The recorded job's own measured cost, or None when unknown."""
    try:
        costs = json.loads(recorded_costs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = costs.get(str(job_id))
    return entry if isinstance(entry, dict) else None


def recorded_cost_line(job_id: str) -> str:
    """One line: the recorded night's own cost and cache share, by job id."""
    entry = recorded_cost_for(job_id)
    if entry is None:
        return ""
    try:
        usd = float(entry["usd"])
        inputs = int(entry["input_tokens"])
        cached = int(entry["cached_tokens"])
    except (KeyError, TypeError, ValueError):
        return ""
    from app import pages as pages_mod
    share = (100.0 * cached / inputs) if inputs else 0.0
    return (f"<p class=\"measured\">Recorded night "
            f"{html.escape(job_id)} cost ${usd:.2f};"
            f" {share:.0f}% of input tokens served from cache. "
            f"{pages_mod.tag('code')}</p>")


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
                f"{esc(display_check_name(payload.get('name', '?')))}: <b>{mark}</b> — "
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


#: Start-up failures of background Night B nights, by job id.
_NIGHT_B_ERRORS: dict[str, str] = {}


def _visitor_question_card(question: dict) -> str:
    """The recorded question with live answer buttons, plus the Night B control."""
    from app import night_b as night_b_mod
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
        "<details><summary>Change one fact instead</summary>"
        "<p>Night A, the venue letter as it is: "
        f"<i>{esc(night_b_mod.night_a_sentence())}</i></p>"
        "<p>Night B, one line changed: "
        f"<i>{esc(night_b_mod.night_b_sentence())}</i></p>"
        f"{night_b_comparison_paragraph()}"
        '<form method="post" action="/visitor/night-b">'
        "<button type=\"submit\">Run the night with this fact</button>"
        "</form>"
        "<p><small>A fresh night from 21:30 on a new copy: same policy,"
        " same permission, one fixture line changed. It runs compressed"
        " and shows each step as it is logged.</small></p>"
        "</details>"
        "</section>"
    )


def night_b_comparison_paragraph() -> str:
    """One scored sentence beside the control, or empty with no data."""
    from app import night_b as night_b_mod
    line = night_b_mod.comparison_line()
    if not line:
        return ""
    return f"<p>{html.escape(line)}</p>"


@app.get("/", response_class=HTMLResponse)
def index(state: str = "") -> str:
    """The one product screen: replay of the recorded hero run.

    `?state=night|question|morning` deep links select one state; the
    default (and direct calls) render the full night-then-question page.
    """
    from app import pages as pages_mod
    from app import replay as replay_mod
    from app import states as states_mod

    resolved = replay_mod.resolve_recorded_job()
    if resolved is None:
        body = (pages_mod.header_row("")
                + "<h1>Night Shift</h1><p>No recorded run yet.</p>")
        return pages_mod.shell("Night Shift", "night", body)
    record = resolved["record"]
    events = replay_mod.replay_events(record)
    full_events = list(record.get("events") or [])
    model = pages_mod.model_for_events(full_events)
    chip = pages_mod.chip_recorded(resolved["date"], model)
    question = next(
        (e for e in reversed(events) if e.get("kind") == "question"), None
    )
    state = (state or "").strip().lower()
    if state == "morning":
        return render_morning_page(
            f"Recorded run {resolved['job_id']}", full_events)
    strip = pages_mod.supplier_strip(states_mod.strip_rows_for(events))
    raw_url = ("https://github.com/hrminator/night-shift/blob/main/data/runs"
               f"/job-{resolved['job_id']}.json")
    footer = pages_mod.footer(raw_url, RESULTS_URL)
    recline = pages_mod.recorded_line(resolved["date"], model)
    cost = recorded_cost_line(resolved["job_id"])
    card = ""
    if question is not None:
        card = _visitor_question_card(question)
    night_detail = (
        f"{states_mod.feed_html(events)}"
        f"{states_mod.beat_html(events)}"
        f"{scan_grounding_section(events)}"
        '<section aria-label="How it decided">'
        '<h2 class="sec">How it decided</h2>'
        f"{states_mod.checks_html(events)}"
        f"{states_mod.decision_html(events)}"
        f"{states_mod.deadline_html(events)}"
        f"{states_mod.skip_html()}</section>"
    )
    if state == "night":
        verdict = states_mod.verdict_2230(events)
        if verdict is not None:
            status_text = "No need to wake you."
        else:
            status_text = ("Overnight replay: one job, 21:30 to the"
                           " question.")
        inst = (pages_mod.clock_block(
            "00:38", event_tag="SCRIPTED TEST EVENT")
            + pages_mod.status_para(status_text) + strip)
        detail = night_detail + cost
        body_class = ""
    elif state == "question":
        if question is not None:
            status_text = str(
                (question.get("payload") or {}).get("question", ""))
        else:
            status_text = ("Overnight replay: one job, 21:30 to the"
                           " question.")
        inst = (pages_mod.clock_block("00:47", amber_dot=True)
                + pages_mod.status_para(status_text) + strip)
        detail = card + cost
        body_class = "state-b"
    else:
        if question is not None:
            status_text = str(
                (question.get("payload") or {}).get("question", ""))
        else:
            status_text = ("Overnight replay: one job, 21:30 to the"
                           " question.")
        inst = (pages_mod.clock_block("00:47", amber_dot=True)
                + pages_mod.status_para(status_text) + strip)
        detail = night_detail + card + cost
        body_class = ""
    body = (pages_mod.header_row(chip)
            + recline
            + '<div class="grid"><div class="inst">'
            + inst + '</div><div class="detail">' + detail + "</div></div>"
            + footer)
    return pages_mod.shell("Night Shift", "night", body,
                           body_class=body_class)


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


def _grounding_verdict() -> dict:
    """The latest grounding-probe verdict, or {} when it never ran."""
    from app import grounding as grounding_mod
    try:
        raw = (grounding_mod.FIXTURES / "grounding_verdict.json").read_text(
            encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def scan_grounding_section(events: list) -> str:
    """The scan page with the model's box, or the quoted line underlined.

    Draws the box from the night's own line_located event only, and only
    when the probe verdict is PASS. Otherwise shows the page with the
    quoted line underlined from lines.json. Empty when the night ran no
    grounding call. Never adds a box after the fact.
    """
    from app import grounding as grounding_mod
    esc = html.escape
    grounded = [event for event in events
                if event.get("kind") in ("line_located",
                                         "line_not_located")]
    if not grounded:
        return ""
    event = grounded[-1]
    payload = event.get("payload") or {}
    line_text = str(payload.get("line_text") or "")
    try:
        png_bytes = grounding_mod.SCAN_PNG_PATH.read_bytes()
    except OSError:
        return ""
    size = grounding_mod.png_size_of()
    if size is None:
        return ""
    width, height = size
    png_url = "data:image/png;base64," + base64.b64encode(
        png_bytes).decode("ascii")
    verdict = _grounding_verdict()
    passed = verdict.get("passed")
    overlay = ""
    caption = "Line Muse Spark quoted"
    box = payload.get("bbox") if event.get("kind") == "line_located" else None
    if (isinstance(box, dict) and verdict.get("verdict") == "PASS"
            and isinstance(passed, int)):
        try:
            left = float(box["x_min"]) / 10
            top = float(box["y_min"]) / 10
            span_w = (float(box["x_max"]) - float(box["x_min"])) / 10
            span_h = (float(box["y_max"]) - float(box["y_min"])) / 10
        except (KeyError, TypeError, ValueError):
            box = None
        else:
            overlay = (
                '<div style="position:absolute;'
                f"left:{left:.1f}%;top:{top:.1f}%;"
                f"width:{span_w:.1f}%;height:{span_h:.1f}%;"
                'outline:3px solid #f59e0b"></div>')
            caption = ("Muse Spark located the line it quoted "
                       f"(grounding call; {passed} of 10 probes on target)")
    if not overlay:
        band = grounding_mod.find_band(line_text)
        if band is not None:
            left = band["x_left"] / width * 100
            top = band["y_bottom"] / height * 100
            span_w = (band["x_right"] - band["x_left"]) / width * 100
            overlay = (
                '<div style="position:absolute;'
                f"left:{left:.1f}%;top:{top:.1f}%;width:{span_w:.1f}%;"
                'border-top:3px solid #1d4ed8"></div>')
    return (
        "<section><h2>Revised quote: the line it quoted</h2>"
        f"<blockquote>{esc(line_text)}</blockquote>"
        '<div style="position:relative;max-width:595px">'
        f'<img src="{png_url}" alt="scan-styled revised quote page" '
        'style="width:100%;display:block">'
        f"{overlay}</div>"
        f"<p>{esc(caption)}</p>"
        "<p><small>Scan-styled fixture page rendered by "
        "scripts/make_fixtures.py (not a real scan).</small></p>"
        "</section>")


def _decision_section(events: list) -> str:
    esc = html.escape
    checks = [e for e in events if e["kind"] == "check"]
    decisions = [e for e in events if e["kind"] == "decision"]
    claims = {e["id"]: e for e in events if e["kind"] == "claim"}
    if not checks and not decisions:
        return ""
    items = "".join(f"<li>{esc(display_check_name((c['payload'] or {}).get('name', '?')))}: {esc(str((c['payload'] or {}).get('result', '?')))} — {esc(str((c['payload'] or {}).get('note', '')))}</li>" for c in checks)
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
        return f"check {display_check_name(payload.get('name', '?'))}: {payload.get('result', '?')} — {str(payload.get('note', ''))[:200]}"
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
    if kind == "line_located":
        return f"grounding: located the quoted line {payload.get('bbox', '?')}"
    if kind == "line_not_located":
        return f"grounding: line not located ({payload.get('reason', '?')})"
    if kind == "provenance":
        policy = str(payload.get("policy_hash", "?"))[:12]
        fixtures = str(payload.get("fixture_hash", "?"))[:12]
        return (f"audit: {payload.get('variant', '?')} night, policy"
                f" {policy}…, fixtures {fixtures}…")
    if kind == "model_call":
        return (f"model call ({payload.get('call_type', '?')}):"
                f" {payload.get('seconds', '?')} s,"
                f" {payload.get('input_tokens', '?')} in /"
                f" {payload.get('output_tokens', '?')} out")
    if kind == "night_error":
        return f"night failed: {payload.get('error', '')}"
    if kind == "step_failed":
        return f"Step failed: {payload.get('reason', '')}"
    if kind == "push_sent":
        return f"push sent to subscription {payload.get('subscription_id', '?')} (HTTP {payload.get('status_code', '?')})"
    if kind == "push_failed":
        return f"push failed for subscription {payload.get('subscription_id', '?')}"
    if kind == "push_skipped":
        return f"push skipped ({payload.get('reason', '?')})"
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

    summary = runner_mod.run_job(variant=variant, owner_job=True)
    return RedirectResponse(url=f"/jobs/{summary['job_id']}", status_code=303)


def _audit_section(events: list) -> str:
    """One job's audit facts: policy, model, effort, fixtures, change."""
    esc = html.escape
    found = [e for e in events if e["kind"] == "provenance"]
    if not found:
        return ("<p>Audit: not recorded"
                 " (this job predates the audit view).</p>")
    payload = found[-1]["payload"] or {}
    rows = (
        "<li>Policy SHA-256:"
        f" <code>{esc(str(payload.get('policy_hash', '?')))}</code></li>"
        f"<li>Model: {esc(str(payload.get('model', '?')))}"
        f" · effort: {esc(str(payload.get('effort', '?')))}</li>"
        "<li>Fixture set SHA-256:"
        f" <code>{esc(str(payload.get('fixture_hash', '?')))}</code></li>"
    )
    if payload.get("changed_line"):
        rows += (
            "<li>Changed line"
            f" ({esc(str(payload.get('changed_file', '')))}):"
            f" <i>{esc(str(payload.get('changed_line')))}</i></li>"
        )
    return f"<section><h2>Audit</h2><ul>{rows}</ul></section>"


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
        f"{_audit_section(events)}"
        f"{card}{_decision_section(events)}{scan_grounding_section(events)}<h2>Events in order</h2><ol>{rows}</ol>"
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


def _is_owner_note(draft: dict) -> bool:
    to = str((draft.get("payload") or {}).get("to", "")).lower()
    return "owner" in to


def _current_heads(events: list) -> list:
    from app import gateway as gateway_mod
    smap = gateway_mod.superseded_map_for(events)
    return [d for d in _draft_head_events(events) if d["id"] not in smap]


def _approval_heads(events: list) -> list:
    return [d for d in _current_heads(events) if not _is_owner_note(d)]


def _for_you_heads(events: list) -> list:
    return [d for d in _current_heads(events) if _is_owner_note(d)]


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
    for draft in [d for d in _draft_head_events(events) if d["id"] not in _smap and not _is_owner_note(d)]:
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
    for_you = ""
    for draft in [d for d in _draft_head_events(events) if d["id"] not in _smap and _is_owner_note(d)]:
        payload = draft["payload"] or {}
        version = payload.get("version", 1)
        state = _draft_state(job_id, draft)
        leak = ("<p><b>Not sent: recipient not in your contacts</b></p>" if payload.get("leak") else "")
        for_you += ("<section><h3>" f"{esc(str(payload.get('purpose', 'message')))} · {esc(state)}" f" · v{esc(str(version))}</h3>" f"<p>To: {esc(str(payload.get('to', '')))}</p>" f"<p>Subject: {esc(str(payload.get('subject', '')))}</p>" f"<blockquote>{esc(str(payload.get('body', '')))}</blockquote>" f"{leak}</section>")
    if for_you:
        cards += "<section><h2>For you</h2>" + for_you + "</section>"
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


def _push_delivery_line(job_id: str | None, events: list) -> str:
    """One push line for owner jobs, else empty. Exact strings only."""
    if job_id is None:
        return ""
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None or not job.get("owner_job"):
        return ""
    sent = [e for e in events if e["kind"] == "push_sent"]
    if sent:
        stamp = str(sent[-1].get("created_at") or "")
        hhmm = stamp[11:16] if len(stamp) >= 16 else ""
        if hhmm:
            return f"Delivered by web push to the owner's phone at {hhmm}"
        return "Delivered by web push to the owner's phone"
    if any(e["kind"] == "push_failed" for e in events):
        return "Web push failed"
    return ""


def _notification_section(job_id: str | None, events: list) -> str:
    """The night's question plus, for owner jobs, the push line below it."""
    esc = html.escape
    questions = [e for e in events if e["kind"] == "question"]
    if not questions:
        return ""
    first = questions[0]
    payload = first["payload"] or {}
    section = (
        "<h2>Notification</h2>"
        f"<p>{esc(str(payload.get('question', '')))} "
        f"(asked {esc(str(first.get('virtual_time', '')))})</p>"
    )
    line = _push_delivery_line(job_id, events)
    if line:
        section += f"<p>{esc(line)}</p>"
    return section


def _morning_job_links(job_id: str | None, events: list) -> str:
    """Raw-log link for live jobs, plus an answer link when one is open."""
    if job_id is None:
        return ""
    from app import store as store_mod

    esc = html.escape
    links = (f'<p><a href="/jobs/{esc(job_id)}/events">Raw event log'
             " (JSON)</a></p>")
    job = store_mod.get_job(job_id)
    if job is not None and job.get("status") == "waiting_for_owner" \
            and any(e["kind"] == "question" for e in events):
        links += (f'<p><a href="/jobs/{esc(job_id)}">Answer the open'
                  " question</a></p>")
    return links


def render_morning_page(job_title: str, events: list, banner: str = "",
                        job_id: str | None = None) -> str:
    """Morning page HTML for live jobs and recorded runs alike."""
    esc = html.escape
    effects = [e for e in events if e["kind"] == "effect"]
    drafts = [e for e in events if e["kind"] == "draft"]
    checks = [e for e in events if e["kind"] == "gateway_check"]
    evidence = [e for e in events if e["kind"] == "check"]
    evidence_rows = "".join(
        "<li>"
        f"{esc(display_check_name((c['payload'] or {}).get('name', '?')))}: "
        f"{esc(str((c['payload'] or {}).get('result', '?')))} — "
        f"{esc(str((c['payload'] or {}).get('note', '')))}"
        "</li>"
        for c in evidence
    )
    evidence_section = (
        f"<h2>Evidence checks</h2><ol>{evidence_rows}</ol>" if evidence else ""
    )
    approval_count = len(_approval_heads(events))
    approval_word = "approval" if approval_count == 1 else "approvals"
    draft_word = "draft" if approval_count == 1 else "drafts"
    if effects:
        label = (
            "Vestland slot held until 09:00 · Done: comparison, hold, "
            f"{approval_count} {draft_word} · Needs you: {approval_count} {approval_word} (the Vestland order before "
            "09:00) · Couldn't verify: Baltic's arrival · Supplier system "
            "and mail simulated"
        )
    else:
        label = (
            "No hold was placed · Done: comparison, drafts · "
            f"Needs you: {approval_count} {approval_word} · Couldn't verify: Baltic's arrival · "
            "Supplier system and mail simulated"
        )
    ack = ""
    for effect in effects:
        payload = effect["payload"] or {}
        ack += (
            "<section><h2>Hold acknowledgement</h2>"
            f"<p>{esc(str(payload.get('acknowledgement', '')))}</p></section>"
        )
    notification = _notification_section(job_id, events)
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
        f"{notification}"
        f"{scan_grounding_section(events)}"
        f"<h2>Drafts awaiting your OK on the exact text</h2>{cards}"
        f"<h2>Outbox (Simulated delivery)</h2>{_outbox_section(events)}"
        f"<h2>How it decided (gateway checks)</h2><details><summary>Gateway checks: {sum(1 for c in checks if (c.get('payload') or {}).get('passed'))} of {len(checks)} pass (tap to expand)</summary><ol>{check_rows}</ol></details>"
        f"{evidence_section}"
        f"{_morning_job_links(job_id, events)}"
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


@app.get("/jobs/{job_id}/events")
def job_events(job_id: str):
    """One job's raw event log as JSON, in stored order."""
    from app import store as store_mod

    job = store_mod.get_job(job_id)
    if job is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return {"job_id": job_id, "status": job.get("status"),
            "events": store_mod.list_events(job_id)}


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


def _recorded_morning_b(note: str):
    """Serve the recorded Night B morning page with a guard notice."""
    from app import replay as replay_mod

    resolved = replay_mod.resolve_recorded_night_b()
    if resolved is None:
        return _recorded_morning(note)
    banner = f"<p><b>{html.escape(note)}</b></p>"
    return render_morning_page(
        f"Recorded Night B {resolved['job_id']}",
        list(resolved["record"].get("events") or []), banner)


def _run_night_b_background(job_id: str, owner: str, slot: str,
                            run_lock: str, day: str) -> None:
    """Run one fresh Night B night; always release the slot and lock."""
    from app import night_b as night_b_mod
    from app import spend as spend_mod
    from app import store as store_mod

    try:
        night_b_mod.run_fresh_night_b(
            respond_fn=_spend_wrapping_respond(job_id, day), job_id=job_id)
    except Exception as exc:  # noqa: BLE001 - a failed night still releases
        _NIGHT_B_ERRORS[job_id] = f"{type(exc).__name__}: {exc}"
        job = store_mod.get_job(job_id)
        if job is not None:
            virtual_time = str(job.get("virtual_time") or "21:30")
            store_mod.append_event(
                job_id, virtual_time, "night_error",
                {"error": _NIGHT_B_ERRORS[job_id][:500]})
            store_mod.set_job_status(job_id, status="failed",
                                     current_step="night_b",
                                     virtual_time=virtual_time)
    finally:
        store_mod.release_lock(run_lock, owner)
        spend_mod.release_visitor_slot(slot, owner)


@app.post("/visitor/night-b")
def visitor_night_b():
    """Run one fact changed: a fresh Night B night on a new job id."""
    import threading
    import uuid

    from app import night_b as night_b_mod
    from app import spend as spend_mod
    from app import store as store_mod

    total, cap = spend_mod.spend_status()
    if total >= cap:
        return _recorded_morning_b(
            f"Live resume unavailable (daily spend cap of ${cap:.2f} "
            "reached; showing the recorded morning page).")
    owner = uuid.uuid4().hex[:12]
    slot = spend_mod.acquire_visitor_slot(owner)
    if slot is None:
        return _recorded_morning_b(
            "Live resume unavailable (2 live resumes already running; "
            "showing the recorded morning page).")
    job_id = night_b_mod.new_night_b_job_id()
    run_lock = f"job:{job_id}:run"
    if not store_mod.acquire_lock(run_lock, owner, ttl_seconds=900):
        spend_mod.release_visitor_slot(slot, owner)
        return _recorded_morning_b(
            "Live resume unavailable (2 live resumes already running; "
            "showing the recorded morning page).")
    thread = threading.Thread(
        target=_run_night_b_background,
        args=(job_id, owner, slot, run_lock, spend_mod.today_utc()),
        daemon=True)
    thread.start()
    return RedirectResponse(url=f"/visitor/night/{job_id}", status_code=303)


def _night_b_elapsed(events: list) -> dict[int, int]:
    """Elapsed seconds per event since the night's first event."""
    from datetime import datetime
    stamps: dict[int, int] = {}
    start = None
    for event in events:
        try:
            moment = datetime.fromisoformat(
                str(event.get("created_at") or ""))
        except ValueError:
            continue
        if start is None:
            start = moment
        stamps[int(event.get("id", 0))] = max(
            int((moment - start).total_seconds()), 0)
    return stamps


@app.get("/visitor/night/{job_id}", response_class=HTMLResponse)
def visitor_night_progress(job_id: str):
    """A fresh Night B night, each real step as it is logged.

    Polls every 2 s while the night runs; every row shown was already in
    the event log, with elapsed seconds. Ends on the copy's morning page.
    """
    from app import night_b as night_b_mod
    from app import store as store_mod

    esc = html.escape
    job = store_mod.get_job(job_id)
    if job is None:
        error = _NIGHT_B_ERRORS.get(job_id)
        if error is not None:
            return (
                "<!doctype html><html><head><title>Night B failed"
                "</title></head>"
                f"<body>{FRONT_CSS}<h1>Night B · Job {esc(job_id)}</h1>"
                f"<p>The night failed to start: {esc(error)}</p>"
                '<p><a href="/">Back to Night Shift</a></p></body></html>'
            )
        return (
            "<!doctype html><html><head><title>Night B starting</title>"
            '<meta http-equiv="refresh" content="1"></head>'
            f"<body>{FRONT_CSS}<h1>Night B · Job {esc(job_id)}</h1>"
            "<p>Starting the night from 21:30…</p>"
            '<p><a href="/">Back to Night Shift</a></p></body></html>'
        )
    events = store_mod.list_events(job_id)
    elapsed = _night_b_elapsed(events)
    rows = "".join(
        f"<li><b>{esc(str(e['virtual_time']))}</b>"
        f" (+{elapsed.get(int(e['id']), 0)}s) — "
        f"{esc(_summarize(e['kind'], e['payload'] or {}))}</li>"
        for e in events
    )
    status = str(job.get("status", "?"))
    morning_url = f"/jobs/{esc(job_id)}/morning"
    raw_url = f"/jobs/{esc(job_id)}/events"
    if status in night_b_mod.TERMINAL_STATUSES:
        head = ('<meta http-equiv="refresh" content="0;url='
                f'{morning_url}">')
        state = (
            f"<p>Night complete: {esc(status)}."
            f' <a href="{morning_url}">Morning page</a> ·'
            f' <a href="{raw_url}">Raw event log</a></p>'
        )
    else:
        head = '<meta http-equiv="refresh" content="2">'
        state = ("<p>The night is running, compressed. Each step below"
                 " appeared when it was logged.</p>")
    return (
        "<!doctype html><html><head><title>Night B live</title>"
        f"{head}</head>"
        f"<body>{FRONT_CSS}<h1>Night B · Job {esc(job_id)}</h1>"
        f"<p>Status: {esc(status)}</p>"
        f"{state}"
        f"<ol>{rows}</ol>"
        f'<p><a href="{raw_url}">Raw event log</a> ·'
        ' <a href="/">Back to Night Shift</a></p></body></html>'
    )


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


def _owner_token_ok(request: Request) -> bool:
    """The owner-phone token rule: header or ?token=, never echoed."""
    expected = os.environ.get("RUN_TOKEN", "")
    if not expected:
        return False
    if request.headers.get("x-run-token", "") == expected:
        return True
    token = request.query_params.get("token", "")
    return bool(token) and token == expected


def _owner_forbidden():
    return HTMLResponse(
        "<h1>Forbidden</h1>"
        "<p>The owner's phone page needs the run token.</p>",
        status_code=403,
    )


@app.get("/owner/phone", response_class=HTMLResponse)
def owner_phone_page(request: Request):
    """Subscribe the owner's phone for web push (token-guarded)."""
    if not _owner_token_ok(request):
        return _owner_forbidden()
    from app import push as push_mod

    public_key = push_mod.vapid_public_key()
    note = ""
    if not public_key:
        note = ("<p><b>Push is not configured on this server "
                "(no VAPID public key).</b></p>")
    return (
        "<!doctype html><html><head><title>Owner phone</title></head>"
        f"<body>{FRONT_CSS}<h1>Owner phone</h1>"
        "<p>Subscribe this phone to receive the night's question by web "
        "push. Only the operator's own job pushes; visitor jobs stay "
        "simulated.</p>"
        f"{note}"
        '<p id="status">Not subscribed yet.</p>'
        '<button id="subscribe" type="button">Subscribe this phone</button>'
        "<p id=\"subscribed\" hidden>This phone is subscribed as the "
        "owner's phone</p>"
        '<button id="test" type="button">Send test push</button>'
        '<p id="test-result"></p>'
        "<p><small>Tip: open this page with ?token=... so the buttons "
        "can call back.</small></p>"
        "<script>"
        f"const VAPID_PUBLIC_KEY = {json.dumps(public_key)};"
        "function pageToken() {"
        " try { return new URLSearchParams(window.location.search)"
        ".get('token') || ''; } catch (e) { return ''; } }"
        "function withToken(path) { const t = pageToken();"
        " return t ? path + '?token=' + encodeURIComponent(t) : path; }"
        "function setStatus(text) {"
        " document.getElementById('status').textContent = text; }"
        "function keyToBytes(base64) {"
        " const pad = '='.repeat((4 - (base64.length % 4)) % 4);"
        " const raw = window.atob(base64.replace(/-/g, '+')"
        ".replace(/_/g, '/') + pad);"
        " const out = new Uint8Array(raw.length);"
        " for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);"
        " return out; }"
        "document.getElementById('subscribe')"
        ".addEventListener('click', async () => {"
        " try {"
        " if (!('serviceWorker' in navigator)"
        " || !('PushManager' in window)) {"
        " setStatus('This browser has no web push support.'); return; }"
        " if (!VAPID_PUBLIC_KEY) {"
        " setStatus('Push is not configured on this server.'); return; }"
        " setStatus('Registering...');"
        " const reg = await navigator.serviceWorker.register('/static/sw.js');"
        " const permission = await Notification.requestPermission();"
        " if (permission !== 'granted') {"
        " setStatus('Notification permission was not granted.'); return; }"
        " setStatus('Subscribing...');"
        " const sub = await reg.pushManager.subscribe({ userVisibleOnly: true,"
        " applicationServerKey: keyToBytes(VAPID_PUBLIC_KEY) });"
        " const data = sub.toJSON(); data.label = 'owner phone';"
        " const resp = await fetch(withToken('/owner/phone/subscribe'),"
        " { method: 'POST', headers: { 'Content-Type': 'application/json' },"
        " body: JSON.stringify(data) });"
        " if (!resp.ok) { setStatus('Subscribe failed (HTTP '"
        " + resp.status + ').'); return; }"
        " document.getElementById('subscribed').hidden = false;"
        " setStatus('Subscribed.');"
        " } catch (e) { setStatus('Subscribe failed: '"
        " + (e && e.message ? e.message : e)); } });"
        "document.getElementById('test')"
        ".addEventListener('click', async () => {"
        " const out = document.getElementById('test-result');"
        " out.textContent = 'Sending...';"
        " try {"
        " const resp = await fetch(withToken('/owner/phone/test'),"
        " { method: 'POST' });"
        " const data = await resp.json();"
        " out.textContent = 'Test push: HTTP ' + resp.status"
        " + ' ' + JSON.stringify(data);"
        " } catch (e) { out.textContent = 'Test push failed: '"
        " + (e && e.message ? e.message : e); } });"
        "</script>"
        "</body></html>"
    )


@app.post("/owner/phone/subscribe")
async def owner_phone_subscribe(request: Request):
    """Store one phone subscription (same token rule)."""
    if not _owner_token_ok(request):
        return JSONResponse({"ok": False, "reason": "forbidden"},
                            status_code=403)
    from app import store as store_mod

    try:
        data = await request.json()
    except ValueError:
        return JSONResponse({"ok": False, "reason": "invalid JSON"},
                            status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"ok": False, "reason": "invalid JSON"},
                            status_code=400)
    endpoint = data.get("endpoint")
    keys = data.get("keys")
    if (not isinstance(endpoint, str) or not endpoint.strip()
            or not isinstance(keys, dict)
            or not isinstance(keys.get("p256dh"), str)
            or not str(keys.get("p256dh")).strip()
            or not isinstance(keys.get("auth"), str)
            or not str(keys.get("auth")).strip()):
        return JSONResponse(
            {"ok": False, "reason": "needs endpoint and keys.p256dh/auth"},
            status_code=400)
    label = data.get("label")
    stored = store_mod.save_push_subscription(
        endpoint.strip(),
        {"p256dh": str(keys["p256dh"]).strip(),
         "auth": str(keys["auth"]).strip()},
        label if isinstance(label, str) else "")
    return {"ok": True, "id": stored["id"]}


@app.post("/owner/phone/test")
async def owner_phone_test(request: Request):
    """Send a test push to every live subscription (same token rule)."""
    if not _owner_token_ok(request):
        return JSONResponse({"ok": False, "reason": "forbidden"},
                            status_code=403)
    from datetime import datetime, timezone

    from app import push as push_mod

    if not push_mod.push_configured():
        return {"ok": False, "reason": "disabled"}
    try:
        asked = await request.json()
    except ValueError:
        asked = {}
    if not isinstance(asked, dict):
        asked = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    title = asked.get("title") or "Night Shift test"
    body = asked.get("body") or f"Test push at {now}"
    results = push_mod.send_to_all(
        str(title)[:200], str(body)[:500], "/")
    return {"ok": True, "results": results}
