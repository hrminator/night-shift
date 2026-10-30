"""Film mode (S1b Part 3): true 16:9 / 9:16 compositions of the replayed beats.

`?film=1&frame=16x9` plays the recorded night from film/cues.json; `?beat=`
renders a single beat alone. Server-rendered from the recorded events, every
model word word for word; no forms, no skip link, cursor hidden. The JS film
scheduler reads the inlined cue sheet and exposes window.__nightShiftTick.

Same view layer as states.py/morning.py: a few underscore helpers are reused
so the diff rule, the greeting and the receipt stay defined in one place.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from fastapi.responses import HTMLResponse

from app import pages as pages_mod
from app import states as states_mod

#: Canonical clocks; actual event times win where a beat has its own event.
DAWN_BEAT = "dawn"
MORNING_BEAT = "morning"


def cues_path() -> Path:
    """The one cue sheet the voice-over is timed against."""
    return Path(__file__).resolve().parent.parent / "film" / "cues.json"


def load_cues() -> dict:
    """The cue sheet: beat names and durations in ms."""
    return json.loads(cues_path().read_text(encoding="utf-8"))


def _payload(event: dict) -> dict:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _reads(events: list) -> list:
    """The 22:30 source reads, same rule as the front-door feed."""
    early = [e for e in states_mod.claims(events)
             if str(e.get("virtual_time", "")) < "00:38"]
    return early or states_mod.claims(events)[:6]


def _revised_vt(events: list) -> str:
    revised = states_mod.revised_of(events)
    if revised is not None:
        stamp = str(revised.get("virtual_time", ""))
        if len(stamp) == 5 and stamp[2] == ":":
            return stamp
    return "00:38"


def _beat_section(name: str, clock: str, kicker: str, theme: str,
                  inner: str, background: str = "") -> str:
    esc = html.escape
    return (
        f'<section class="fbeat" data-beat="{esc(name)}"'
        f' data-clock="{esc(clock)}" data-kicker="{esc(kicker)}"'
        f' data-theme="{esc(theme)}">{background}'
        f'<div class="fc">{inner}</div>'
        "</section>"
    )


def _brief_inner() -> str:
    return (
        "<p class=\"fserif\">The owner hands over the brief and goes to "
        "bed.</p>"
        "<p class=\"fsub\">100 tote bags · Bergen customer day, Thu Nov 12 "
        "· budget NOK 3,500</p>"
        "<p class=\"fsub quiet\">Fictional studio and suppliers · real Muse "
        f"Spark calls · night compressed.</p>"
        f"<div class=\"tagrow left\">{pages_mod.tag('code')}</div>"
    )


def _read_inner(events: list) -> str:
    esc = html.escape
    rows = "".join(
        "<div class=\"fread\" data-frow>"
        f"<p class=\"fsrc\">{esc(str(e.get('virtual_time', '?')))} · "
        f"{esc(str(_payload(e).get('source', '?')))}</p>"
        "<p class=\"fquote\">"
        f"{esc(str(_payload(e).get('quote', '')))}</p></div>"
        for e in _reads(events)
    )
    return (f"<div class=\"fgrid6\">{rows}</div>"
            f"<div class=\"tagrow left\">{pages_mod.tag('spark')}</div>")


def _verdict_inner(events: list) -> str:
    esc = html.escape
    verdict = states_mod.verdict_2230(events)
    if verdict is None:
        return "<p class=\"fserif\">No 22:30 verdict in this run.</p>"
    return (
        "<p class=\"fserif\">No need to wake you.</p>"
        f"<p class=\"freason\">"
        f"{esc(str(_payload(verdict).get('reason', '')))}</p>"
        f"<div class=\"tagrow left\">{pages_mod.tag('spark')}</div>"
    )


def _sheet_inner(events: list) -> str:
    esc = html.escape
    quote_id, replaces_id, _original, revised_line = (
        states_mod._quote_lines(events))
    if not revised_line:
        return "<p class=\"fserif\">No revised quote in this run.</p>"
    return (
        "<div class=\"sheet fsheet\">"
        "<p class=\"firm\">Rannavere Print OÜ (fictional)</p>"
        f"<h3>Quote {esc(quote_id)} — 100 tote bags with your logo</h3>"
        f"<p>This quote replaces quote {esc(replaces_id)}.</p>"
        "<div class=\"gap\"></div>"
        "<p>Price: NOK 18 per bag<br>Freight: NOK 350<br>"
        "Total: NOK 2,150</p>"
        "<div class=\"gap\"></div>"
        f"<p class=\"quoted\">{esc(revised_line)}</p>"
        "<div class=\"gap\"></div>"
        "<p>Contact: quotes@rannavere-print.example.com (fictional)</p>"
        "</div>"
        f"<p class=\"sheetcap\">Line Muse Spark quoted"
        f"{pages_mod.tag('spark')}</p>"
    )


def _diff_inner(events: list) -> str:
    esc = html.escape
    _quote_id, _replaces_id, original, revised_line = (
        states_mod._quote_lines(events))
    if not original or not revised_line:
        return "<p class=\"fserif\">No before/after lines in this run.</p>"
    return (
        "<div class=\"fdiff\">"
        f"<s>{esc(states_mod._diff_text(original))}</s>"
        f"<strong>{esc(states_mod._diff_text(revised_line))}</strong>"
        f"<div class=\"tagrow left\">{pages_mod.tag('code')}</div>"
        "</div>"
    )


def _checks_inner(events: list) -> str:
    esc = html.escape
    picked = states_mod.checks_for_decision(events)
    if not picked:
        return "<p class=\"fserif\">No checks in this run.</p>"
    cards = "".join(
        "<div class=\"fcard\" data-fcard>"
        f"<p class=\"ftitle\">"
        f"{esc(states_mod.check_title(_payload(e).get('name', '?')))}</p>"
        f"{states_mod._check_mark(str(_payload(e).get('result', 'fail')))}"
        f"<p class=\"fnote2\">{esc(str(_payload(e).get('note', '')))}</p>"
        f"<div class=\"tagrow left\">{pages_mod.tag('spark')}</div>"
        "</div>"
        for e in picked
    )
    return f"<div class=\"fchecks\">{cards}</div>"


def _decision_inner(events: list) -> str:
    esc = html.escape
    decision = states_mod.wake_decision(events)
    if decision is None:
        return "<p class=\"fserif\">No decision in this run.</p>"
    outcome = str(_payload(decision).get("outcome", "?")).replace(
        "_", " ").title()
    return (
        f"<p class=\"fserif\">{esc(outcome)}, because …</p>"
        f"<p class=\"freason\">"
        f"{esc(str(_payload(decision).get('reason', '')))}</p>"
        f"<div class=\"tagrow left\">{pages_mod.tag('spark')}</div>"
    )


def _note_inner(events: list) -> str:
    from app import clock as clock_mod
    esc = html.escape
    question = states_mod.question_of(events)
    if question is None:
        return "<p class=\"fserif\">No question in this run.</p>"
    payload = _payload(question)
    options = "".join(
        f"<button class=\"btn {'fill' if pos == 0 else 'ghost'}\""
        f" type=\"button\" tabindex=\"-1\">{esc(str(option))}</button>"
        for pos, option in enumerate(payload.get("options") or [])
    )
    return (
        "<div class=\"fnote\">"
        "<p class=\"fask\">Muse Spark asks</p>"
        f"<h2>{esc(str(payload.get('question', '')))}</h2>"
        f"{options}"
        f"<p class=\"fans\">answer by "
        f"{esc(clock_mod.fmt(clock_mod.answer_deadline()))}</p>"
        f"<div class=\"tagrow\">{pages_mod.tag('spark')}</div>"
        "</div>"
    )


def _dawn_inner() -> str:
    return (
        '<div class="fdawn" aria-hidden="true">'
        '<div class="fdawn-band"></div><div class="fdawn-veil"></div></div>'
    )


def _morning_inner(events: list) -> str:
    from app import main as main_mod
    from app import morning as morning_mod
    esc = html.escape
    hold_id, ack = morning_mod._hold_of(events)
    count = len(main_mod._approval_heads(events))
    word = "approval" if count == 1 else "approvals"
    chip = ("<p><span class=\"holdchip\">HOLD LAPSES 09:00</span></p>"
            if hold_id is not None else "")
    receipt = morning_mod._receipt_html(ack) if hold_id is not None else ""
    return (
        "<div class=\"fmorn\"><div>"
        f"<p class=\"fserif\">{esc(morning_mod._greeting(events))}</p>"
        f"{chip}"
        f"<p class=\"fcounts\">Needs you: {count} {word} on the exact "
        "text.</p>"
        f"<div class=\"tagrow left\">{pages_mod.tag('code')}</div>"
        f"</div>{receipt}</div>"
    )


def _beat_clock(events: list, name: str) -> str:
    """One beat's clock from its own event, else the canonical beat."""
    if name in ("brief", "read"):
        return "21:30" if name == "brief" else "22:30"
    if name in ("sheet", "diff"):
        return _revised_vt(events)
    if name == "verdict":
        verdict = states_mod.verdict_2230(events)
        if verdict is not None:
            return str(verdict.get("virtual_time", "22:30"))
        return "22:30"
    if name == "checks":
        picked = states_mod.checks_for_decision(events)
        if picked:
            return str(picked[0].get("virtual_time", "00:39"))
        return "00:39"
    if name == "decision":
        decision = states_mod.wake_decision(events)
        if decision is not None:
            return str(decision.get("virtual_time", "00:39"))
        return "00:39"
    if name == "note":
        return states_mod.beat_time(events, "checkpoint", "00:47")
    return "07:00"


def _beat_kicker(name: str, clock: str, events: list) -> str:
    if name == "read":
        return f"{clock} · {len(_reads(events))} reads"
    label = {
        "brief": "the handoff",
        "verdict": "no need to wake you",
        "sheet": "the beat",
        "diff": "one verb changed",
        "checks": "what it checked",
        "decision": "decision record",
        "note": "Muse Spark asks",
        "dawn": "the dawn",
        "morning": "the morning",
    }[name]
    return f"{clock} · {label}"


def render_film_page(resolved: dict, frame: str = "",
                     beat: str = "") -> str | HTMLResponse:
    """The film page: the recorded night as camera compositions."""
    shape = "9x16" if (frame or "").strip() == "9x16" else "16x9"
    try:
        cues = load_cues()
        names = [entry["name"] for entry in cues["beats"]]
    except (OSError, ValueError, KeyError, TypeError):
        return HTMLResponse("<h1>No cue sheet yet</h1>", status_code=404)
    want = (beat or "").strip()
    if want and want not in names:
        return HTMLResponse("<h1>Unknown beat</h1>", status_code=404)
    from app import replay as replay_mod
    record = resolved["record"]
    events = replay_mod.replay_events(record)
    full_events = list(record.get("events") or [])
    # The morning beat needs the whole night (effect, drafts, approvals).
    builders = {
        "brief": lambda: _brief_inner(),
        "read": lambda: _read_inner(events),
        "verdict": lambda: _verdict_inner(events),
        "sheet": lambda: _sheet_inner(events),
        "diff": lambda: _diff_inner(events),
        "checks": lambda: _checks_inner(events),
        "decision": lambda: _decision_inner(events),
        "note": lambda: _note_inner(events),
        "dawn": lambda: _dawn_inner(),
        "morning": lambda: _morning_inner(full_events),
    }
    shown = [want] if want else names
    backgrounds = {"dawn": _dawn_inner()}
    sections = "".join(
        _beat_section(
            name, _beat_clock(events, name),
            _beat_kicker(name, _beat_clock(events, name), events),
            "paper" if name == MORNING_BEAT else "night",
            "" if name == DAWN_BEAT else builders[name](),
            backgrounds.get(name, ""))
        for name in shown
    )
    model = pages_mod.model_for_events(full_events)
    first = shown[0]
    first_clock = _beat_clock(events, first)
    hour, _, minute = first_clock.partition(":")
    kick = _beat_kicker(first, first_clock, events)
    overlay = (
        "<div class=\"fclock\">"
        "<div class=\"fclock-t\">"
        f"<span class=\"h\">{html.escape(hour)}</span>"
        "<span class=\"c\">:</span>"
        f"<span class=\"m\">{html.escape(minute)}</span></div>"
        f"<div class=\"fkick\">{html.escape(kick)}</div>"
        f"<div class=\"fprov\">RECORDED · {html.escape(resolved['date'])}"
        f" · {html.escape(model.upper())}</div></div>"
    )
    cues_json = json.dumps(cues).replace("</", "<\\/")
    stage = (
        f"<div class=\"fstage\" id=\"fstage\" data-beat=\"{html.escape(want)}\">"
        f"{sections}</div>"
        "<script type=\"application/json\" id=\"cues\">"
        f"{cues_json}</script>"
    )
    theme = "paper" if want == MORNING_BEAT else "night"
    return pages_mod.shell(f"Night Shift film {shape}", theme,
                           overlay + stage,
                           body_class=f"film frame-{shape}")
