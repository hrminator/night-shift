"""Virtual scenario clock: Tue Nov 3 21:30 -> Wed Nov 4 09:30, Europe/Oslo.

Code, not the model, computes the deadline chain from the 02:00 cutoff:
answer due = cutoff - 10 min = 01:50, latest safe notification = 01:50 - 20
min = 01:30. The clock advances only by explicit runner calls (no sleeping).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")
NIGHT_START_DATE = date(2026, 11, 3)  # a Tuesday; the night runs into Nov 4
NIGHT_NEXT_DATE = date(2026, 11, 4)

HANDOFF = "21:30"
REVISED_QUOTE_ARRIVED = "00:38"
CUTOFF = "02:00"
ANSWER_DUE = "01:50"
LATEST_SAFE_NOTIFICATION = "01:30"
MORNING_REVIEW = "07:00"
HOLD_LAPSE = "09:00"
NIGHT_END = "09:30"


def _date_for(hour: int) -> date:
    # Evening hours belong to Nov 3; small hours belong to Nov 4.
    return NIGHT_START_DATE if hour >= 12 else NIGHT_NEXT_DATE


def at(virtual_hhmm: str) -> datetime:
    hour, minute = (int(part) for part in virtual_hhmm.split(":"))
    return datetime.combine(
        _date_for(hour), time(hour, minute), tzinfo=OSLO
    )


def to_minutes(virtual_hhmm: str) -> int:
    hour, minute = (int(part) for part in virtual_hhmm.split(":"))
    return hour * 60 + minute


def is_at_or_before(first_hhmm: str, second_hhmm: str) -> bool:
    return at(first_hhmm) <= at(second_hhmm)


def cutoff() -> datetime:
    return at(CUTOFF)


def answer_deadline() -> datetime:
    return cutoff() - timedelta(minutes=10)


def latest_safe_notification() -> datetime:
    return answer_deadline() - timedelta(minutes=20)


def fmt(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def deadline_facts_line() -> str:
    return (
        f"latest safe notification {fmt(latest_safe_notification())}, "
        f"answer by {fmt(answer_deadline())}, cutoff {fmt(cutoff())}"
    )
