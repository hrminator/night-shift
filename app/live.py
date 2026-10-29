"""Live visitor paths (S1a Part 5): background resume + progress pages.

POST /visitor/answer copies the recorded run and resumes it in a background
thread under the same daily spend cap and 2-resume semaphore as Night B;
GET /visitor/answer/{id} shows the real steps as they are logged, each with
its elapsed seconds, in the v2 style. No spinner: the running step is the
loading state, and the chip reads LIVE while it runs. Cap and slot refusals
serve the recorded morning with a one-line notice and the chip on RECORDED.
"""

from __future__ import annotations

import html
import threading
import urllib.parse
import uuid

from fastapi.responses import HTMLResponse, RedirectResponse

from app import pages as pages_mod
from app import states as states_mod


async def post_answer(request):
    """Answer as the owner: copy the recorded run and resume it live."""
    from app import main as main_mod
    from app import replay as replay_mod
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
        return main_mod._recorded_morning(
            f"Live resume unavailable (daily spend cap of ${cap:.2f} "
            "reached; showing the recorded morning page).")
    owner = uuid.uuid4().hex[:12]
    slot = spend_mod.acquire_visitor_slot(owner)
    if slot is None:
        return main_mod._recorded_morning(
            "Live resume unavailable (2 live resumes already running; "
            "showing the recorded morning page).")
    try:
        new_id = replay_mod.copy_job_for_visitor(
            resolved["record"], choice)
    except ValueError as exc:
        spend_mod.release_visitor_slot(slot, owner)
        return HTMLResponse(f"<h1>Cannot resume</h1><p>{exc}</p>",
                            status_code=400)
    run_lock = f"job:{new_id}:run"
    if not store_mod.acquire_lock(run_lock, owner, ttl_seconds=900):
        spend_mod.release_visitor_slot(slot, owner)
        return main_mod._recorded_morning(
            "Live resume unavailable (2 live resumes already running; "
            "showing the recorded morning page).")
    thread = threading.Thread(
        target=_run_answer_background,
        args=(new_id, owner, slot, run_lock, spend_mod.today_utc()),
        daemon=True)
    thread.start()
    return RedirectResponse(url=f"/visitor/answer/{new_id}", status_code=303)


def _run_answer_background(job_id: str, owner: str, slot: str,
                           run_lock: str, day: str) -> None:
    """Resume one visitor copy; always release the slot and lock."""
    from app import main as main_mod
    from app import runner as runner_mod
    from app import spend as spend_mod
    from app import store as store_mod

    try:
        runner_mod.resume_job(
            job_id,
            respond_fn=main_mod._spend_wrapping_respond(job_id, day))
    except Exception as exc:  # noqa: BLE001 - a failed night still releases
        main_mod._NIGHT_B_ERRORS[job_id] = f"{type(exc).__name__}: {exc}"
        job = store_mod.get_job(job_id)
        if job is not None:
            virtual_time = str(job.get("virtual_time") or "01:05")
            store_mod.append_event(
                job_id, virtual_time, "night_error",
                {"error": main_mod._NIGHT_B_ERRORS[job_id][:500]})
            store_mod.set_job_status(job_id, status="failed",
                                     current_step="resume",
                                     virtual_time=virtual_time)
    finally:
        store_mod.release_lock(run_lock, owner)
        spend_mod.release_visitor_slot(slot, owner)


def _unknown_job_page(job_id: str, title: str) -> str:
    """Progress fallback while the background thread still starts."""
    from app import main as main_mod
    error = main_mod._NIGHT_B_ERRORS.get(job_id)
    chip = pages_mod.chip_live(job_id, running=error is None)
    if error is not None:
        detail = (f"<p>The night failed to start: {html.escape(error)}</p>")
        head = ""
    else:
        detail = "<p>Starting the night from 21:30…</p>"
        head = '<meta http-equiv="refresh" content="1">'
    body = (pages_mod.header_row(chip)
            + pages_mod.clock_block("21:30")
            + pages_mod.status_para(title)
            + f"<section><div class=\"card\">{detail}</div></section>"
            + pages_mod.footer(f"/jobs/{html.escape(job_id)}/events",
                               main_mod.RESULTS_URL, job_id))
    return pages_mod.shell(title, "night", body, head_extra=head)


def _progress_page(job_id: str, title: str, status_sentence: str,
                   answer_note: bool) -> str:
    """One live night: every logged step with elapsed seconds, no spinner."""
    from app import main as main_mod
    from app import night_b as night_b_mod
    from app import store as store_mod

    esc = html.escape
    job = store_mod.get_job(job_id)
    if job is None:
        return _unknown_job_page(job_id, title)
    events = store_mod.list_events(job_id)
    elapsed = main_mod._night_b_elapsed(events)
    status = str(job.get("status", "?"))
    terminal = status in night_b_mod.TERMINAL_STATUSES
    rows = ""
    for pos, event in enumerate(events):
        running = " class=\"running\"" if (
            not terminal and pos == len(events) - 1) else ""
        summary = main_mod._summarize(
            event["kind"], event["payload"] or {})
        seconds = elapsed.get(int(event["id"]), 0)
        rows += (
            f"<li{running}><span class=\"st\">"
            f"{esc(str(event['virtual_time']))}</span><div>"
            f"{esc(summary)} "
            f"<span class=\"el\">(+{seconds}s)</span></div></li>"
        )
    morning_url = f"/jobs/{esc(job_id)}/morning"
    raw_url = f"/jobs/{esc(job_id)}/events"
    dawn_html = ""
    if terminal:
        # The dawn plays, then the morning shows: JS drives #dawn for 3 s
        # and forwards to ?dawn=1; the meta refresh is the no-JS path.
        head = ('<meta http-equiv="refresh" content="4;url='
                f'{morning_url}?dawn=1">')
        state = (
            f"<p>Night complete: {esc(status)}."
            f" <a href=\"{morning_url}\">Morning page</a> ·"
            f" <a href=\"{raw_url}\">Raw event log</a></p>"
        )
        dawn_html = (
            '<div id="dawn" data-target="'
            f'{morning_url}?dawn=1" aria-hidden="true">'
            '<div class="dawn-band"></div><div class="dawn-veil"></div></div>')
    else:
        head = '<meta http-equiv="refresh" content="2">'
        state = ("<p>The night is running, compressed. Each step below"
                 " appeared when it was logged.</p>")
    note = ""
    if answer_note:
        answers = [e for e in events if e["kind"] == "owner_answer"]
        if answers:
            voted = str(answers[-1].get("virtual_time", ""))
            note = (f"<p class=\"small\">Answer recorded {esc(voted)}. "
                    "Your answer is a fact. The permission is from the "
                    "21:30 brief.</p>")
    tick = str(job.get("virtual_time") or "01:05")
    inst = pages_mod.stick(pages_mod.clock_block(tick, amber_dot=not terminal)
            + pages_mod.status_para(status_sentence)
            + pages_mod.supplier_strip(states_mod.strip_rows_for(events)))
    detail = (note + state
              + "<section aria-label=\"Steps\">"
              "<p class=\"lab\">Steps as logged</p>"
              f"<div class=\"card\"><ol class=\"steps\">{rows}</ol>"
              f"<div class=\"tagrow\">{pages_mod.tag('code')}</div>"
              "</div></section>")
    body = (pages_mod.header_row(
        pages_mod.chip_live(job_id, running=not terminal))
        + '<div class="grid"><div class="inst">'
        + inst + '</div><div class="detail">' + detail + "</div></div>"
        + dawn_html
        + pages_mod.footer(raw_url, main_mod.RESULTS_URL, job_id))
    return pages_mod.shell(title, "night", body, head_extra=head)


def answer_progress_page(job_id: str) -> str:
    """One visitor copy resuming: real steps as they are logged."""
    return _progress_page(job_id, f"Night Shift live copy {job_id}",
                          "Resuming your copy of the night.",
                          answer_note=True)


def night_progress_page(job_id: str) -> str:
    """One fresh Night B night: real steps as they are logged."""
    return _progress_page(job_id, f"Night B · Job {job_id}",
                          "Running the night with one fact changed.",
                          answer_note=False)
