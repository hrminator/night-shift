"""State bodies for the product screen (S1a Parts 2-4).

State A (the night), State B (the question) and State C (the morning)
rendered from a job's own events in the v2 layout. Every model word comes
from the event log word for word; check titles come from the runner's own
CHECK_DEFINITIONS; deadlines come from the clock. View layer only.
"""

from __future__ import annotations

import html
import re

from app import clock as clock_mod
from app import pages as pages_mod

#: Stored events keep the old sixth-check name; pages show the new one.
CHECK_DISPLAY_NAMES = {"can_ask_now": "can_ask_supplier_or_venue_now"}


def display_check_name(name: object) -> str:
    """Name shown on pages for one evidence check."""
    return CHECK_DISPLAY_NAMES.get(str(name), str(name))


def check_title(name: object) -> str:
    """One check's plain-language question from the runner's definition."""
    from app import runner as runner_mod
    definition = runner_mod.CHECK_DEFINITIONS.get(display_check_name(name))
    if not definition:
        return display_check_name(name)
    text = definition.strip()
    return text[:1].upper() + text[1:] + "?"


def _payload(event: dict) -> dict:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def claims(events: list) -> list:
    """Claim events in stored order."""
    return [e for e in events if e.get("kind") == "claim"]


def checks(events: list) -> list:
    """Check events in stored order."""
    return [e for e in events if e.get("kind") == "check"]


def decisions(events: list) -> list:
    """Decision events in stored order."""
    return [e for e in events if e.get("kind") == "decision"]


def question_of(events: list) -> dict | None:
    """The latest question event, or None."""
    found = [e for e in events if e.get("kind") == "question"]
    return found[-1] if found else None


def revised_of(events: list) -> dict | None:
    """The revised-quote event (the 00:38 beat), or None."""
    found = [e for e in events if e.get("kind") == "revised_quote"]
    return found[-1] if found else None


def _check_results(events: list) -> dict[str, str]:
    """Latest result per check name (display names)."""
    results: dict[str, str] = {}
    for event in checks(events):
        payload = _payload(event)
        name = display_check_name(payload.get("name", "?"))
        if payload.get("result") in ("pass", "fail"):
            results[name] = str(payload.get("result"))
    return results


def strip_rows_for(events: list, morning: bool = False,
                   hold_id: str | None = None) -> list[tuple[str, str, str]]:
    """Supplier strip rows derived from one job's own checks and effects."""
    results = _check_results(events)
    oslo = "Too slow"
    if results.get("nordtrykk_can_make_nov10") == "pass":
        oslo = "On time"
    van = "Van to the venue only"
    if morning and hold_id:
        van = f"Held until 09:00 · {hold_id}"
    elif morning:
        van = "Slot went at 02:00"
    cheap = "Arrival unverified"
    if revised_of(events) is None \
            and results.get("baltic_arrival_committed") == "pass":
        cheap = "On time, plan of record"
    return [
        ("the Oslo printer", "Nordtrykk AS", oslo),
        ("the guaranteed van", "Vestland Tekstil", van),
        ("the cheap one", "Baltic Print OÜ", cheap),
    ]


def verdict_2230(events: list) -> dict | None:
    """The 22:30 no-wake decision, when the night logged one."""
    for event in decisions(events):
        payload = _payload(event)
        if payload.get("outcome") in ("no_wake", "wait_for_morning"):
            return event
    return None


def wake_decision(events: list) -> dict | None:
    """The wake decision after the 00:38 event, else the last decision."""
    revised = revised_of(events)
    after = [e for e in decisions(events)
             if revised is None or int(e.get("id", 0)) > int(
                 revised.get("id", 0))]
    wakes = [e for e in after if _payload(e).get("outcome") == "wake"]
    if wakes:
        return wakes[-1]
    pool = after or decisions(events)
    return pool[-1] if pool else None


def checks_for_decision(events: list) -> list:
    """The six named checks behind the decision (post-00:38 when present)."""
    from app import runner as runner_mod
    revised = revised_of(events)
    pool = [e for e in checks(events)
            if revised is None or int(e.get("id", 0)) > int(
                revised.get("id", 0))]
    if not pool:
        pool = checks(events)
    latest: dict[str, dict] = {}
    for event in pool:
        name = display_check_name(_payload(event).get("name", "?"))
        latest[name] = event
    ordered = [latest[name] for name in runner_mod.CHECK_NAMES
               if name in latest]
    if ordered:
        return ordered
    return pool[-6:]


def _reads(events: list) -> list:
    """Source reads: the 22:30 claims (the six reads)."""
    early = [e for e in claims(events)
             if str(e.get("virtual_time", "")) < "00:38"]
    return early or claims(events)[:6]


def feed_html(events: list) -> str:
    """State A feed: handoff, collapsed reads, 22:30 verdict, 00:38 row."""
    esc = html.escape
    rows = []
    if any(e.get("kind") == "handoff" for e in events):
        rows.append(
            "<div class=\"frow\"><span class=\"ftime\">21:30</span><div>"
            "<p>The owner hands over the brief and goes to bed.</p>"
            f"<p>{pages_mod.tag('code')}</p>"
            "<p class=\"quiet\">Fictional studio and suppliers · real Muse"
            " Spark calls · night compressed.</p></div></div>"
        )
    reads = _reads(events)
    if reads:
        count = len(reads)
        noun = "source" if count == 1 else "sources"
        cards = "".join(
            f"<div class=\"read sub\"><p class=\"src\">"
            f"{esc(str(e.get('virtual_time', '?')))} · "
            f"{esc(str(_payload(e).get('source', '?')))}</p>"
            f"<blockquote class=\"quote\">"
            f"{esc(str(_payload(e).get('quote', '')))}</blockquote>"
            f"<div class=\"tagrow\">{pages_mod.tag('spark')}</div></div>"
            for e in reads
        )
        rows.append(
            "<div class=\"frow\"><span class=\"ftime\">22:30</span><div>"
            f"<details><summary class=\"foldrow\">"
            f"<span class=\"foldname\">Read {count} {noun}</span>"
            "<span class=\"chev\" aria-hidden=\"true\"></span>"
            f"</summary><div class=\"foldbody\">{cards}</div></details>"
            f"<p>{pages_mod.tag('spark')}</p></div></div>"
        )
    verdict = verdict_2230(events)
    if verdict is not None:
        payload = _payload(verdict)
        rows.append(
            "<div class=\"frow\"><span class=\"ftime\">"
            f"{esc(str(verdict.get('virtual_time', '22:30')))}</span><div>"
            "<p class=\"verdict\">No need to wake you.</p>"
            f"<p class=\"quote\">{esc(str(payload.get('reason', '')))}</p>"
            f"<p>{pages_mod.tag('spark')}</p></div></div>"
        )
    revised = revised_of(events)
    if revised is not None:
        payload = _payload(revised)
        rows.append(
            "<div class=\"frow\"><span class=\"ftime\">"
            f"{esc(str(revised.get('virtual_time', '00:38')))}</span><div>"
            f"<p>The cheap one&rsquo;s revised quote "
            f"{esc(str(payload.get('quote', '?')))} arrives and replaces "
            f"{esc(str(payload.get('replaces', '?')))}.</p>"
            f"<p>{pages_mod.tag('sim')}</p></div></div>"
        )
    if not rows:
        return ""
    return (
        "<section aria-label=\"Feed\" id=\"state-night\">"
        "<p class=\"lab\">The night so far</p>"
        f"<div class=\"card\">{''.join(rows)}</div></section>"
    )


def _quote_lines(events: list) -> tuple[str, str, str, str]:
    """(quote id, replaces id, original line, revised line) for the beat.

    The lines are the claims' own quoted delivery commitments; empty when
    the night logged no Baltic quote claims.
    """
    revised = revised_of(events)
    quote_id = str((_payload(revised).get("quote", "Q-1187-B"))
                   if revised is not None else "Q-1187-B")
    replaces_id = str((_payload(revised).get("replaces", "Q-1187"))
                      if revised is not None else "Q-1187")
    original = ""
    revised_line = ""
    for event in claims(events):
        payload = _payload(event)
        source = str(payload.get("source", ""))
        quote = str(payload.get("quote", ""))
        if "Q-1187-B" in source or "revised" in source.lower():
            if "replaces" in quote.lower():
                continue
            if len(quote) > len(revised_line):
                revised_line = quote
        elif "Q-1187" in source or "Q-1187" in quote:
            if len(quote) > len(original):
                original = quote
    return quote_id, replaces_id, original, revised_line


def _diff_text(quote: str) -> str:
    """The diff shows the commitment without its Delivery label."""
    text = re.sub(r"(?i)^\s*delivery\s*:\s*", "", quote.strip())
    return text[:-1] if text.endswith(".") else text


def beat_html(events: list) -> str:
    """The 00:38 beat: paper sheet, CODE diff, one caption. No box ever."""
    esc = html.escape
    quote_id, replaces_id, original, revised_line = _quote_lines(events)
    if not revised_line:
        return ""
    sheet = (
        "<div class=\"sheet\">"
        "<p class=\"firm\">Baltic Print OÜ (fictional)</p>"
        f"<h3>Quote {esc(quote_id)} — 100 tote bags with your logo</h3>"
        f"<p>This quote replaces quote {esc(replaces_id)}.</p>"
        "<div class=\"gap\"></div>"
        "<p>Price: NOK 18 per bag<br>Freight: NOK 350<br>"
        "Total: NOK 2,150</p>"
        "<div class=\"gap\"></div>"
        f"<p class=\"quoted\">{esc(revised_line)}</p>"
        "<div class=\"gap\"></div>"
        "<p>Contact: quotes@baltic-print.example.com (fictional)</p>"
        "</div>"
        f"<p class=\"sheetcap\">{pages_mod.ICONS['file']}"
        "Line Muse Spark quoted"
        f"{pages_mod.tag('spark')}</p>"
    )
    diff = ""
    if original:
        diff = (
            "<div class=\"diff card\">"
            f"<s>{esc(_diff_text(original))}</s>"
            f"<strong>{esc(_diff_text(revised_line))}</strong>"
            f"<div class=\"tagrow\">{pages_mod.tag('code')}</div>"
            "</div>"
        )
    return (
        "<section aria-label=\"The revised quote\">"
        "<p class=\"lab\">00:38 · the beat</p>"
        f"{sheet}{diff}"
        "<p class=\"beatcap\">Same price. One verb changed. Muse Spark"
        " caught it from pixels.</p></section>"
    )


def _check_mark(result: str) -> str:
    if result == "pass":
        return (
            "<span class=\"yn ok\"><svg class=\"ic\" width=\"20\" height=\"20\""
            " viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\""
            " stroke-width=\"1.5\" stroke-linecap=\"round\""
            " stroke-linejoin=\"round\" aria-hidden=\"true\">"
            "<path d=\"M20 6 9 17l-5-5\"/></svg></span>"
        )
    return "<span class=\"yn no\">No</span>"


def checks_html(events: list, meta: str = "00:39–00:46",
                open_fold: bool = True) -> str:
    """The six checks as plain-language questions with the model's notes."""
    esc = html.escape
    picked = checks_for_decision(events)
    if not picked:
        return ""
    cards = "".join(
        "<div class=\"check sub\"><div class=\"check-top\">"
        f"<span class=\"check-title\">"
        f"{esc(check_title(_payload(e).get('name', '?')))}</span>"
        f"{_check_mark(str(_payload(e).get('result', 'fail')))}</div>"
        f"<p class=\"note\">{esc(str(_payload(e).get('note', '')))}</p>"
        "<div class=\"check-foot\">"
        f"<span class=\"hint\">"
        f"{esc(display_check_name(_payload(e).get('name', '?')))}</span>"
        f"{pages_mod.tag('spark')}</div></div>"
        for e in picked
    )
    flag = " open" if open_fold else ""
    return (
        f"<details class=\"fold\"{flag}>"
        "<summary class=\"foldrow card\">"
        "<span class=\"foldname\">What it checked</span>"
        f"<span class=\"foldmeta\">{esc(meta)}</span>"
        "<span class=\"chev\" aria-hidden=\"true\"></span></summary>"
        f"<div class=\"foldbody\">{cards}</div></details>"
    )


def decision_html(events: list) -> str:
    """The decision record in the model's own words."""
    esc = html.escape
    decision = wake_decision(events)
    if decision is None:
        return ""
    payload = _payload(decision)
    outcome = str(payload.get("outcome", "?")).replace("_", " ").title()
    return (
        "<section aria-label=\"Decision\">"
        f"<p class=\"lab\">Decision record · "
        f"{esc(str(decision.get('virtual_time', '?')))}</p>"
        "<div class=\"decision card\">"
        f"<p class=\"because\">{esc(outcome)}, because …</p>"
        f"<p class=\"quote\">{esc(str(payload.get('reason', '')))}</p>"
        f"<div class=\"tagrow\">{pages_mod.tag('spark')}</div>"
        "</div></section>"
    )


def deadline_html(events: list) -> str:
    """The deadline line, computed by code, tagged CODE."""
    esc = html.escape
    latest = clock_mod.fmt(clock_mod.latest_safe_notification())
    due = clock_mod.fmt(clock_mod.answer_deadline())
    cutoff = clock_mod.fmt(clock_mod.cutoff())
    question = question_of(events)
    woke = ""
    if question is not None:
        woke = (f" · woke you "
                f"{esc(str(question.get('virtual_time', '?')))}")
    return (
        f"<p class=\"deadline\">{pages_mod.ICONS['clock']}"
        f"<span>Latest safe time to wake you {latest}{woke} · answer by "
        f"{due} · slot closes {cutoff} {pages_mod.tag('code')}</span></p>"
    )


def skip_html() -> str:
    """Pinned text link into State B."""
    return "<div class=\"skip\"><a href=\"?state=question\">Skip to 00:47</a></div>"
