"""State C: the paper morning page (S1a Part 4).

The v2 morning layout with the two marks applied (receipt under the strip
in the left column, larger; staggered timeline labels come from the shared
stylesheet): greeting from the job's own events, HOLD LAPSES chip, strip,
thermal receipt, approval letters exactly as counted, For-you notes, Done,
Couldn't-verify, What-was-saved, collapsed How-it-decided, resume panel
with the job's own token numbers, cost line, gateway facts on tap. The
no-hold morning reads just as finished. View layer only.
"""

from __future__ import annotations

import html

from app import clock as clock_mod
from app import ledger as ledger_mod
from app import pages as pages_mod
from app import states as states_mod

#: The matched replay finding, as published in the README (F4b part 3).
REPLAY_MATCHED_SENTENCE = (
    "In the matched replay experiment, resume with replayed reasoning used "
    "a mean of 53,253 input tokens vs 132,037 with the source documents "
    "re-sent (results/replay-matched-20261028T202510Z/)."
)

#: Letter headings by draft purpose; unknown purposes show as-is.
PURPOSE_LABELS = {
    "order": "The van order",
    "venue_note": "The venue note",
    "baltic_note": "The cheap one’s note",
}

#: One-word outbox labels by draft purpose.
PURPOSE_SHORT = {
    "order": "Order",
    "venue_note": "Venue note",
    "baltic_note": "Baltic note",
}


def _payload(event: dict) -> dict:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _effects(events: list) -> list:
    return [e for e in events if e.get("kind") == "effect"]


def _hold_of(events: list) -> tuple[str | None, str]:
    """(hold id, acknowledgement) from the first effect, or (None, "")."""
    effects = _effects(events)
    if not effects:
        return None, ""
    payload = _payload(effects[0])
    hold_id = payload.get("hold_id")
    ack = str(payload.get("acknowledgement", ""))
    return (hold_id.strip() if isinstance(hold_id, str)
            and hold_id.strip() else None, ack)


def _label_line(events: list) -> str:
    """The morning label line, with this job's own counts."""
    from app import main as main_mod
    approval_count = len(main_mod._approval_heads(events))
    approval_word = "approval" if approval_count == 1 else "approvals"
    draft_word = "draft" if approval_count == 1 else "drafts"
    if _effects(events):
        return (
            "Vestland slot held until 09:00 · Done: comparison, hold, "
            f"{approval_count} {draft_word} · Needs you: {approval_count} "
            f"{approval_word} (the Vestland order before "
            "09:00) · Couldn't verify: Baltic's arrival · Supplier system "
            "and mail simulated"
        )
    return (
        "No hold was placed · Done: comparison, drafts · "
        f"Needs you: {approval_count} {approval_word} · Couldn't verify: "
        "Baltic's arrival · Supplier system and mail simulated"
    )


def _greeting(events: list) -> str:
    """The Newsreader greeting, chosen by the job's own effect."""
    if _effects(events):
        return ("Good morning. The guaranteed van’s slot is held for you "
                "until 09:00.")
    return "No hold. The slot went at 02:00. Here’s what’s left."


def _version_short(draft: dict) -> str:
    """One letter's short version stamp, e.g. v·ac7d."""
    from app import gateway as gateway_mod
    return f"v·{gateway_mod.head_version_hash(draft)[:4]}"


def _purpose_label(purpose: str, deadline: str | None) -> str:
    label = PURPOSE_LABELS.get(purpose, purpose)
    if purpose == "order" and deadline:
        return f"{label} · approve before {deadline}"
    return label


def _short_label(purpose: str) -> str:
    return PURPOSE_SHORT.get(purpose, purpose)


def _delivered_for(events: list, draft_id: int) -> dict | None:
    found = [e for e in events if e.get("kind") == "delivered"
             and _payload(e).get("draft_id") == draft_id]
    return found[-1] if found else None


def _leak_line(payload: dict) -> str:
    if payload.get("leak"):
        return "<p><b>Not sent: recipient not in your contacts</b></p>"
    return ""


def _letter_open(draft: dict, label: str) -> str:
    """The top of one paper letter: heading, recipient, subject."""
    esc = html.escape
    payload = _payload(draft)
    return (
        f"<p class=\"lab\">{esc(label)}</p>"
        f"<p class=\"to\">{pages_mod.ICONS['mail']}"
        f"<span>To: {esc(str(payload.get('to', '')))}</span></p>"
        f"<p class=\"subj\">{esc(str(payload.get('subject', '')))}</p>"
    )


def _letter_meta(draft: dict, state: str) -> str:
    return (
        "<div class=\"meta\">"
        f"<span>{esc(_version_short(draft))} · {esc(state)}</span>"
        f"{pages_mod.tag('spark')}</div>"
    )


def esc(text: object) -> str:
    """html.escape without importing html in every helper."""
    return html.escape(str(text))


def _approved_row(draft: dict, delivered: dict | None,
                  approval_time: str) -> str:
    """An approved letter collapsed to one outbox row."""
    payload = _payload(draft)
    when = str((delivered.get("virtual_time")
                if delivered is not None else None) or approval_time)
    label = _short_label(str(payload.get("purpose", "message")))
    return (
        "<details class=\"outbox card\">"
        "<summary class=\"outboxrow\">"
        f"<span>{esc(label)} · approved · {esc(when)} · "
        "SIMULATED DELIVERY</span>"
        f"{pages_mod.tag('sim')}</summary>"
        "<div class=\"foldbody\">"
        f"{_letter_open(draft, _purpose_label(str(payload.get('purpose', '')), None))}"
        f"<p class=\"body\">{esc(payload.get('body', ''))}</p>"
        f"{_letter_meta(draft, 'approved')}"
        "</div></details>"
    )


def _approval_letter(job_id: str, draft: dict, state: str,
                     delivered: dict | None, approval_time: str,
                     with_forms: bool) -> str:
    """One letter needing the owner's OK, editable in place."""
    from app import gateway as gateway_mod
    payload = _payload(draft)
    purpose = str(payload.get("purpose", "message"))
    deadline = gateway_mod.draft_deadline(draft)
    label = _purpose_label(purpose, deadline)
    if state == "approved":
        return _approved_row(draft, delivered, approval_time)
    body_html: str
    if with_forms:
        body_html = (
            f"<form method=\"post\" action=\"/jobs/{esc(job_id)}/edit-draft\">"
            f"<input type=\"hidden\" name=\"draft_id\" value=\"{draft['id']}\">"
            "<input type=\"hidden\" name=\"virtual_time\" value=\"07:00\">"
            f"<textarea class=\"edit\" name=\"body\" rows=\"8\">"
            f"{esc(payload.get('body', ''))}</textarea>"
            "<button class=\"btn savebtn\" data-save type=\"submit\" "
            "disabled>Save edited version</button></form>"
        )
    else:
        body_html = f"<p class=\"body\">{esc(payload.get('body', ''))}</p>"
    forms = ""
    if with_forms:
        version_hash = gateway_mod.head_version_hash(draft)
        forms = (
            f"<form method=\"post\" action=\"/jobs/{esc(job_id)}/approve\">"
            f"<input type=\"hidden\" name=\"draft_id\" value=\"{draft['id']}\">"
            "<input type=\"hidden\" name=\"version_hash\" "
            f"value=\"{version_hash}\">"
            "<input type=\"hidden\" name=\"virtual_time\" value=\"07:00\">"
            "<button class=\"btn\" data-approve type=\"submit\">"
            "Approve this exact text</button></form>"
        )
    return (
        f"<div class=\"letter\" data-draft=\"{draft['id']}\">"
        f"{_letter_open(draft, label)}"
        f"{body_html}"
        f"{_leak_line(payload)}"
        f"{_letter_meta(draft, state)}"
        f"{forms}</div>"
    )


def _needs_section(job_id: str, events: list, with_forms: bool) -> str:
    """Needs-you letters: current external heads, F4a counts."""
    from app import gateway as gateway_mod
    from app import main as main_mod
    heads = main_mod._approval_heads(events)
    count = len(heads)
    word = "approval" if count == 1 else "approvals"
    letters = ""
    for draft in heads:
        state = main_mod._draft_state(job_id, draft)
        delivered = _delivered_for(events, int(draft["id"]))
        key = gateway_mod.draft_key_of(draft)
        approvals = gateway_mod.approvals_for_key(job_id, key)
        when = str((approvals[-1].get("payload") or {}).get(
            "approved_at", "07:00")) if approvals else "07:00"
        letters += _approval_letter(job_id, draft, state, delivered, when,
                                    with_forms)
    return (
        "<section class=\"sec\" aria-label=\"Needs you\">"
        f"<h2>Needs you: {count} {word}</h2>{letters}</section>"
    )


def _for_you_section(events: list) -> str:
    """Owner notes render as letters without any buttons."""
    from app import main as main_mod
    heads = main_mod._for_you_heads(events)
    if not heads:
        return ""
    letters = ""
    for draft in heads:
        payload = _payload(draft)
        letters += (
            "<div class=\"letter\">"
            f"{_letter_open(draft, str(payload.get('purpose', 'message')))}"
            f"<p class=\"body\">{esc(payload.get('body', ''))}</p>"
            f"{_leak_line(payload)}"
            f"{_letter_meta(draft, 'for you')}</div>"
        )
    return ("<section class=\"sec\" aria-label=\"For you\">"
            f"<h2>For you</h2>{letters}</section>")


def _earlier_section(events: list) -> str:
    """Superseded drafts collapsed under Earlier versions, never counted."""
    from app import gateway as gateway_mod
    from app import main as main_mod
    smap = gateway_mod.superseded_map_for(events)
    if not smap:
        return ""
    items = ""
    for draft in main_mod._draft_head_events(events):
        if draft["id"] not in smap:
            continue
        payload = _payload(draft)
        try:
            version = int(payload.get("version", 1))
        except (TypeError, ValueError):
            version = 1
        items += (
            "<section><h3>"
            f"{esc(str(payload.get('purpose', 'message')))} · "
            f"{esc(smap[draft['id']])} · v{version}</h3>"
            f"<p>To: {esc(str(payload.get('to', '')))}</p>"
            f"<p>Subject: {esc(str(payload.get('subject', '')))}</p>"
            f"<blockquote>{esc(str(payload.get('body', '')))}</blockquote>"
            "</section>"
        )
    return ("<details><summary>Earlier versions (superseded drafts "
            "proposed before the 00:38 event)</summary>"
            f"{items}</details>")


def _done_section(events: list) -> str:
    """Done rows: comparison, the hold, the drafts."""
    from app import main as main_mod
    hold_id, _ = _hold_of(events)
    count = len(main_mod._approval_heads(events))
    word = "draft" if count == 1 else "drafts"
    rows = (
        "<div class=\"drow\">"
        f"<span class=\"tickmark\">{pages_mod.ICONS['check']}</span>"
        "<div>Compared the three suppliers on price and verified delivery"
        f"<div class=\"tagrow left\">{pages_mod.tag('code')}</div></div></div>"
    )
    if hold_id is not None:
        rows += (
            "<div class=\"drow\">"
            f"<span class=\"tickmark\">{pages_mod.ICONS['check']}</span>"
            f"<div>Held the guaranteed van’s slot until 09:00 · "
            f"{esc(hold_id)} · no purchase commitment"
            f"<div class=\"tagrow left\">{pages_mod.tag('sim')}</div>"
            "</div></div>"
        )
    if count:
        rows += (
            "<div class=\"drow\">"
            f"<span class=\"tickmark\">{pages_mod.ICONS['check']}</span>"
            f"<div>Prepared {count} {word} for your OK on the exact text"
            f"<div class=\"tagrow left\">{pages_mod.tag('code')}</div>"
            "</div></div>"
        )
    return (f"<section class=\"sec\" aria-label=\"Done\"><h2>Done</h2>"
            f"<div class=\"card\">{rows}</div></section>")


def _dispatch_line(events: list) -> str:
    """The revised quote's dispatch line, from the night's own claim."""
    best = ""
    for event in states_mod.claims(events):
        payload = _payload(event)
        source = str(payload.get("source", ""))
        quote = str(payload.get("quote", ""))
        if "Q-1187-B" not in source and "revised" not in source.lower():
            continue
        if "replaces" in quote.lower():
            continue
        if len(quote) > len(best):
            best = quote
    return best


def _couldnt_section(events: list) -> str:
    """Couldn't-verify: the cheap one's arrival, with its quoted line."""
    line = _dispatch_line(events)
    quote = (f"<p class=\"quote\">{esc(line)}</p>"
             if line else "<p>No delivery commitment found in the log.</p>")
    return (
        "<section class=\"sec\" aria-label=\"Couldn’t verify\">"
        "<h2>Couldn’t verify</h2>"
        "<div class=\"unverified card\">"
        "<p>The cheap one’s arrival. Its revised quote promises only "
        "dispatch:</p>"
        f"{quote}"
        f"<div class=\"tagrow\">{pages_mod.tag('spark')}</div>"
        "</div></section>"
    )


def _ledger_section(events: list) -> str:
    """Who said what: the resume's code-built ledger, when logged."""
    ledgers = [e for e in events if e.get("kind") == "fact_ledger"]
    if not ledgers:
        return ""
    lines = "".join(
        f"<li>{esc(line)}</li>"
        for line in ledger_mod.render_lines(_payload(ledgers[-1])))
    return (
        "<section class=\"sec\" aria-label=\"Who said what\">"
        "<h2>Who said what</h2>"
        f"<div class=\"card\"><ul class=\"evlist\">{lines}</ul>"
        f"<div class=\"tagrow\">{pages_mod.tag('code')}</div>"
        "</div></section>")


def _saved_section(events: list) -> str:
    """What was saved: the chance to decide, never a purchase."""
    if _effects(events):
        sentence = ("What was saved is the chance to decide in the morning, "
                    "not a purchase or a guaranteed delivery.")
    else:
        sentence = ("No hold was placed. The comparison and the drafts above "
                    "are what’s left to decide on.")
    return (
        "<section class=\"sec\" aria-label=\"What was saved\">"
        "<h2>What was saved</h2>"
        f"<p class=\"saved\">{esc(sentence)}</p></section>"
    )


def _notification_block(job_id: str | None, events: list) -> str:
    """The night's question plus, for owner jobs, the push line below it."""
    from app import main as main_mod
    inner = main_mod._notification_section(job_id, events)
    if not inner:
        return ""
    return f"<section class=\"sec\">{inner}</section>"


def _how_section(events: list) -> str:
    """How it decided, collapsed: checks, decision, the quoted line."""
    from app import main as main_mod
    checks = states_mod.checks_html(events, open_fold=False)
    decision = states_mod.decision_html(events)
    scan = main_mod.scan_grounding_section(events)
    if not checks and not decision and not scan:
        return ""
    return (
        "<section class=\"sec\" aria-label=\"How it decided\">"
        "<h2>How it decided</h2>"
        f"{checks}{decision}{scan}</section>"
    )


def _model_call_totals(events: list) -> dict | None:
    """One job's own billed totals from its model_call events, or None."""
    inputs = cached = outputs = calls = 0
    for event in events:
        if event.get("kind") != "model_call":
            continue
        payload = _payload(event)
        try:
            inputs += int(payload.get("input_tokens") or 0)
            cached += int(payload.get("cached_tokens") or 0)
            outputs += int(payload.get("output_tokens") or 0)
        except (TypeError, ValueError):
            continue
        calls += 1
    if not calls:
        return None
    return {"inputs": inputs, "cached": cached, "outputs": outputs,
            "calls": calls}


def _recorded_totals(events: list) -> dict | None:
    """One recorded job's measured totals from data/recorded_costs.json."""
    if not events:
        return None
    from app import main as main_mod
    entry = main_mod.recorded_cost_for(
        str(events[0].get("job_id") or ""))
    if entry is None:
        return None
    try:
        return {"inputs": int(entry["input_tokens"]),
                "cached": int(entry["cached_tokens"]),
                "outputs": int(entry["output_tokens"]),
                "calls": int(entry.get("model_calls", 0))}
    except (KeyError, TypeError, ValueError):
        return None


def _waited_minutes(events: list) -> tuple[str, str, int] | None:
    """(checkpoint time, answer time, waited minutes) for the resume."""
    checkpoints = [e for e in events if e.get("kind") == "checkpoint"]
    answers = [e for e in events if e.get("kind") == "owner_answer"]
    if not checkpoints or not answers:
        return None
    start = str(checkpoints[-1].get("virtual_time", ""))
    end = str(answers[-1].get("virtual_time", ""))
    try:
        minutes = int((clock_mod.at(end) - clock_mod.at(start))
                      .total_seconds() // 60)
    except (ValueError, KeyError):
        return None
    return start, end, minutes


def _resume_panel(events: list) -> str:
    """The resume: waited minutes, pruned files, own tokens, matched line."""
    waited = _waited_minutes(events)
    if waited is None:
        return ""
    start, end, minutes = waited
    pruned = [e for e in events if e.get("kind") == "resume_pruned_files"]
    if pruned:
        try:
            count = int(_payload(pruned[-1]).get("pruned_input_files") or 0)
        except (TypeError, ValueError):
            count = 0
        noun = "PDF" if count == 1 else "PDFs"
        prune_clause = f" ({count} {noun} pruned at resume)" if count else ""
    else:
        prune_clause = ""
    totals = _model_call_totals(events) or _recorded_totals(events)
    if totals is not None:
        tokens = (
            f"This night billed {totals['inputs']:,} input tokens over "
            f"{totals['calls']} calls "
            f"({totals['cached']:,} served from cache). "
            "Usage as reported by the API."
        )
    else:
        tokens = "Usage as reported by the API."
    minute_word = "minute" if minutes == 1 else "minutes"
    return (
        "<div class=\"resume card\">"
        f"<p class=\"lab\">The resume · {esc(end)}</p>"
        f"<p>The night waited {minutes} {minute_word} for the answer "
        f"({esc(start)} → {esc(end)}). It picked up its own reasoning; "
        f"documents not re-sent{prune_clause}.</p>"
        f"<p class=\"tokens\">{esc(tokens)}</p>"
        f"<p>{esc(REPLAY_MATCHED_SENTENCE)}</p>"
        f"<div class=\"tagrow\">{pages_mod.tag('code')}</div>"
        "</div>"
    )


def _cost_line(job_id: str | None, events: list) -> str:
    """Measured cost: the job's own calls, or its recorded entry."""
    from app import main as main_mod
    if job_id is not None:
        totals = _model_call_totals(events)
        if totals is None:
            return ""
        from app.spend import cost_usd
        usd = cost_usd(totals["inputs"], totals["cached"],
                       totals["outputs"])
        share = (100.0 * totals["cached"] / totals["inputs"]
                 if totals["inputs"] else 0.0)
        return (
            f"<p class=\"measured\">Measured: this night cost ${usd:.2f}; "
            f"{share:.0f}% of input tokens served from cache. "
            f"{pages_mod.tag('code')}</p>"
        )
    if not events:
        return ""
    return main_mod.recorded_cost_line(str(events[0].get("job_id") or ""))


def _gateway_fold(events: list) -> str:
    """The gateway's asserted facts, one row per check, on tap."""
    checks = [e for e in events if e.get("kind") == "gateway_check"]
    if not checks:
        return ""
    passed = sum(1 for c in checks if _payload(c).get("passed"))
    rows = "".join(
        "<li>"
        f"{esc(str(_payload(c).get('check', '?')))}: "
        f"{'pass' if _payload(c).get('passed') else 'FAIL'} — "
        f"{esc(str(_payload(c).get('detail', '')))}"
        "</li>"
        for c in checks
    )
    return (
        "<details class=\"fold\">"
        "<summary class=\"foldrow card\">"
        f"<span class=\"foldname\">Gateway checks: {passed} of "
        f"{len(checks)} pass (tap to expand)</span>"
        "<span class=\"chev\" aria-hidden=\"true\"></span></summary>"
        f"<div class=\"foldbody\"><ol class=\"evlist\">{rows}</ol>"
        "</div></details>"
    )


def _receipt_html(ack: str) -> str:
    """The hold acknowledgement as a thermal slip."""
    lines = [line.strip() for line in ack.splitlines() if line.strip()]
    last = lines[-1] if lines else ""
    parts = [part.strip() for part in last.split("·") if part.strip()]
    if len(parts) < 2:
        from app import portal as portal_mod
        last = portal_mod.acknowledgement_text().splitlines()[-1]
        parts = [part.strip() for part in last.split("·")]
    rows = "".join(f"<p>{esc(part)}</p>" for part in parts)
    first = esc(lines[0]) if lines else ""
    return (
        "<section class=\"receiptsec\" aria-label=\"Receipt\">"
        f"<div class=\"receipt wide\">{rows}"
        f"<div class=\"tagrow\">{pages_mod.tag('sim')}</div></div>"
        + (f"<p class=\"small\">{first}</p>" if first else "")
        + "</section>"
    )


def _recorded_date(events: list) -> str:
    try:
        stamp = str(events[0].get("created_at") or "")[:10]
        if stamp:
            return stamp
    except (IndexError, AttributeError):
        pass
    return "unknown date"


def render_morning_page(job_title: str, events: list, banner: str = "",
                        job_id: str | None = None) -> str:
    """Morning page HTML for live jobs and recorded runs alike."""
    from app import main as main_mod
    hold_id, ack = _hold_of(events)
    model = pages_mod.model_for_events(events)
    if job_id is not None:
        chip = pages_mod.chip_live(job_id, running=False)
        raw_url = f"/jobs/{html.escape(job_id)}/events"
    else:
        chip = pages_mod.chip_recorded(_recorded_date(events), model)
        recorded_id = str(events[0].get("job_id") or "") if events else ""
        if recorded_id:
            raw_url = ("https://github.com/hrminator/night-shift/blob/main/"
                       f"data/runs/job-{recorded_id}.json")
        else:
            raw_url = ("https://github.com/hrminator/night-shift/tree/main/"
                       "data/runs")
    notice = f"<div class=\"notice\">{banner}</div>" if banner else ""
    title_line = (
        f"<p class=\"small\">Morning page · 07:00 virtual time · "
        f"{html.escape(job_title)}</p>"
    )
    holdchip = ("<p style=\"margin:0\">"
                "<span class=\"holdchip\">HOLD LAPSES 09:00</span></p>"
                if hold_id is not None else "")
    strip = pages_mod.supplier_strip(
        states_mod.strip_rows_for(events, morning=True, hold_id=hold_id))
    receipt = _receipt_html(ack) if hold_id is not None else ""
    inst = (pages_mod.clock_block("07:00")
            + pages_mod.status_para(_greeting(events))
            + holdchip + strip + receipt)
    lookup = job_id if job_id is not None else job_title
    detail = (
        f"<p class=\"small\"><b>{html.escape(_label_line(events))}</b></p>"
        f"{_needs_section(lookup, events, with_forms=job_id is not None)}"
        f"{_for_you_section(events)}"
        f"{_earlier_section(events)}"
        f"{_done_section(events)}"
        f"{_couldnt_section(events)}"
        f"{_ledger_section(events)}"
        f"{_saved_section(events)}"
        f"{_notification_block(job_id, events)}"
        f"{_how_section(events)}"
        f"{_resume_panel(events)}"
        f"{_cost_line(job_id, events)}"
        f"{_gateway_fold(events)}"
    )
    body = (pages_mod.header_row(chip)
            + title_line + notice
            + '<div class="grid"><div class="inst">'
            + inst + '</div><div class="detail">' + detail + "</div></div>"
            + pages_mod.footer(raw_url, main_mod.RESULTS_URL))
    return pages_mod.shell(f"Night Shift morning · {job_title}", "paper",
                           body)
