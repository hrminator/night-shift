"""Shared page chrome for the Night Shift product screen (S1a).

One shell, one header (wordmark + provenance chip), one clock block with the
night timeline, one serif status sentence, one supplier strip, one footer.
State bodies (night / question / morning / live steps) plug into the shell.
View layer only: every model word comes from the event log, the chip and the
cost line from the recorded costs file and the job's own events.
"""

from __future__ import annotations

import html

from app import clock as clock_mod

#: Google Fonts only, no framework, no build step.
FONTS_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="preload" as="style" href="https://fonts.googleapis.com/css2'
    '?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500'
    '&family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2'
    '?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500'
    '&family=Newsreader:ital,wght@0,400;0,500;1,400&display=swap">'
)

CSS_LINK = '<link rel="stylesheet" href="/static/night.css">'
JS_SCRIPT = '<script src="/static/night.js" defer></script>'

#: Ticks on the night timeline: 21:30 -> 09:30 with the five named beats.
TIMELINE_TICKS = ("22:30", "00:38", "00:47", "02:00", "07:00")

#: The one raised tick label (00:38 and 00:47 sit 1.25% apart).
RAISED_TICK = "00:47"

#: At most five inline Lucide line icons (16 px, 1.5 stroke, currentColor).
_ICON_OPEN = (
    '<svg class="ic" width="16" height="16" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round"'
    ' stroke-linejoin="round" aria-hidden="true">'
)
ICONS = {
    "clock": (
        _ICON_OPEN + '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 6v6l4 2"/></svg>'
    ),
    "file": (
        _ICON_OPEN + '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12'
        'a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>'
    ),
    "check": (
        _ICON_OPEN + '<path d="M20 6 9 17l-5-5"/></svg>'
    ),
    "bell": (
        _ICON_OPEN + '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>'
    ),
    "mail": (
        _ICON_OPEN + '<rect width="20" height="16" x="2" y="4" rx="2"/>'
        '<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>'
    ),
}


def tag(kind: str) -> str:
    """One quiet provenance tag: a 6 px dot plus a word, no box."""
    name = {"spark": "MUSE SPARK", "code": "CODE", "sim": "SIMULATED"}[kind]
    return f'<span class="tag {kind}"><i></i>{name}</span>'


def model_for_events(events: list) -> str:
    """The model id behind one job, from its own events.

    Newest jobs log a provenance event with the model; older ones log a
    model per model_call event. Jobs predating both ran on the product's
    configured model, which the adapter reports.
    """
    for event in reversed(events):
        if event.get("kind") == "provenance":
            model = (event.get("payload") or {}).get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    for event in reversed(events):
        if event.get("kind") == "model_call":
            model = (event.get("payload") or {}).get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    from app.adapter import MODEL
    return MODEL


def chip_recorded(date: str, model: str) -> str:
    """Provenance chip for a replay: RECORDED · date · MODEL."""
    return (
        "<span class=\"chip\">RECORDED · "
        f"{html.escape(date)} · {html.escape(model.upper())}</span>"
    )


def chip_live(job_id: str, running: bool = True) -> str:
    """Provenance chip for a visitor copy, pulsing while a step runs."""
    dot = '<span class="livedot" aria-hidden="true"></span>' if running else ""
    return (
        "<span class=\"chip\">LIVE · YOUR COPY #"
        f"{html.escape(job_id[:4])}{dot}</span>"
    )


def header_row(chip_html: str) -> str:
    """Wordmark plus provenance chip, always visible."""
    return (
        "<header class=\"masthead\">"
        f"<div class=\"wmrow\"><span class=\"wm\">Night Shift</span>"
        f"{chip_html}</div></header>"
    )


def recorded_line(date: str, model: str) -> str:
    """One quiet line under the header naming the recording's own facts."""
    return (
        f"<p class=\"recline\">Real {html.escape(model)} calls recorded on "
        f"{html.escape(date)}. Supplier system and mail simulated.</p>"
    )


def timeline_pct(virtual_hhmm: str) -> float:
    """Position of one virtual time on the 21:30 -> 09:30 line, in percent."""
    span = (clock_mod.at(clock_mod.NIGHT_END)
            - clock_mod.at(clock_mod.HANDOFF)).total_seconds()
    offset = (clock_mod.at(virtual_hhmm)
              - clock_mod.at(clock_mod.HANDOFF)).total_seconds()
    return max(0.0, min(100.0, 100.0 * offset / span))


def clock_block(current: str, event_tag: str | None = None,
                amber_dot: bool = False) -> str:
    """The big clock plus the timeline with its five ticks."""
    esc = html.escape
    hour, _, minute = current.partition(":")
    tag_html = f"<span class=\"evtag\">{esc(event_tag)}</span>" \
        if event_tag else ""
    ticks = "".join(
        f"<span class=\"tick\" style=\"left:{timeline_pct(t):.2f}%\">"
        f"<em{' class=\"up\"' if t == RAISED_TICK else ''}>{t}</em></span>"
        for t in TIMELINE_TICKS
    )
    dot_class = "dot amber" if amber_dot else "dot"
    return (
        "<div class=\"clockblock\">"
        f"<div class=\"clockrow\"><div class=\"clock\">"
        f"<span class=\"h\">{esc(hour)}</span>"
        "<span class=\"c\">:</span>"
        f"<span class=\"m\">{esc(minute)}</span></div>{tag_html}</div>"
        f"<div class=\"tl\" role=\"img\" aria-label=\"Night timeline from "
        f"21:30 to 09:30, now at {esc(current)}\">"
        f"<div class=\"tl-ends\"><span>{clock_mod.HANDOFF}</span>"
        f"<span>{clock_mod.NIGHT_END}</span></div>"
        "<div class=\"tl-line\"></div>"
        f"{ticks}"
        f"<span class=\"{dot_class}\" style=\"left:"
        f"{timeline_pct(current):.2f}%\"></span>"
        "</div></div>"
    )


def status_para(text: str) -> str:
    """The one serif status sentence."""
    return f"<p class=\"status\">{html.escape(text)}</p>"


def supplier_strip(rows: list[tuple[str, str, str]]) -> str:
    """The three-row supplier strip, rendered by code, tagged CODE."""
    parts = "".join(
        f"<div class=\"srow\"><div><span class=\"srole\">"
        f"{html.escape(role)}</span>"
        f"<span class=\"sname\">{html.escape(name)}</span></div>"
        f"<span class=\"sstat\">{html.escape(status)}</span></div>"
        for role, name, status in rows
    )
    return (
        f"<div class=\"strip card\">{parts}"
        f"<div class=\"tagrow\">{tag('code')}</div></div>"
    )


def footer(raw_log_url: str, results_url: str) -> str:
    """Footer: the three-tag legend, links, and the scenario line."""
    esc = html.escape
    return (
        "<footer>"
        "<p class=\"job\">100 tote bags · Bergen customer day, Thu Nov 12 ·"
        " budget NOK 3,500</p>"
        "<p class=\"promise\">Works your job through the night. Built to wake"
        " you only when it must.</p>"
        "<p class=\"fquiet\">Built for nights like this one. Also fits: a"
        " venue booking that expires, a carrier cutoff, a quote that changes"
        " overnight. Only this one is built.</p>"
        "<p class=\"lab\">Where each line comes from</p>"
        "<ul class=\"legend\">"
        f"<li>{tag('spark')}<span>the model wrote or read this, quoted word"
        " for word. It also marks the API&rsquo;s own usage numbers.</span>"
        "</li>"
        f"<li>{tag('code')}<span>code calculated or rendered it; it was not"
        " judged. This includes the strikethrough diff.</span></li>"
        f"<li>{tag('sim')}<span>marks the fictional portal and"
        " mail.</span></li>"
        "</ul>"
        f"<p class=\"links\"><a href=\"/evidence\">Evidence</a> · "
        f"<a href=\"{esc(results_url)}\">Results in the README</a> · "
        f"<a href=\"{esc(raw_log_url)}\">This run&rsquo;s raw event log"
        "</a></p>"
        "<p class=\"scenario\">Fictional studio and suppliers · real Muse"
        " Spark calls · night compressed.</p>"
        "</footer>"
    )


def shell(title: str, theme: str, body_html: str,
          body_class: str = "", head_extra: str = "") -> str:
    """One full page: fonts, shared stylesheet, small JS, grain, wrap."""
    extra = f" {body_class}" if body_class else ""
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>"
        f"{FONTS_HEAD}{CSS_LINK}{JS_SCRIPT}{head_extra}</head>"
        f"<body class=\"{theme}{extra}\">"
        "<div class=\"grain\" aria-hidden=\"true\"></div>"
        f"<div class=\"wrap\">{body_html}</div></body></html>"
    )
