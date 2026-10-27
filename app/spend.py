"""Model spend accounting and live-resume guards.

Spend is computed from token counts with the Spark 1.3 prices ($1.25 input,
$0.15 cached input, $4.25 output per million) and stored per UTC day in the
database. A visitor resume is refused when the day's total has reached the
cap (DAILY_CAP_USD, default $5), or when 2 live resumes already run.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.store import acquire_lock, day_spend_usd, release_lock

INPUT_USD_PER_M = 1.25
CACHED_INPUT_USD_PER_M = 0.15
OUTPUT_USD_PER_M = 4.25

MAX_LIVE_RESUMES = 2
DEFAULT_DAILY_CAP_USD = 5.0


def cost_usd(input_tokens: int, cached_tokens: int,
             output_tokens: int) -> float:
    """Price one model call in USD from its token counts."""
    fresh = max(int(input_tokens or 0) - int(cached_tokens or 0), 0)
    return (fresh * INPUT_USD_PER_M
            + int(cached_tokens or 0) * CACHED_INPUT_USD_PER_M
            + int(output_tokens or 0) * OUTPUT_USD_PER_M) / 1_000_000


def usage_of(result: dict) -> tuple[int, int, int]:
    """Pull (input, cached input, output) tokens from a respond() result."""
    usage = result.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    return (int(usage.get("input_tokens") or 0),
            int(details.get("cached_tokens") or 0),
            int(usage.get("output_tokens") or 0))


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def daily_cap_usd() -> float:
    try:
        return float(os.environ.get("DAILY_CAP_USD",
                                    str(DEFAULT_DAILY_CAP_USD)))
    except ValueError:
        return DEFAULT_DAILY_CAP_USD


def spend_status(path: Path | None = None) -> tuple[float, float]:
    """Return (today's recorded total, cap) in USD."""
    return day_spend_usd(today_utc(), path=path), daily_cap_usd()


def acquire_visitor_slot(owner: str, path: Path | None = None) -> str | None:
    """Take one of the 2 live-resume slots. Returns the slot name or None."""
    for index in range(MAX_LIVE_RESUMES):
        name = f"visitor-resume-{index}"
        if acquire_lock(name, owner, ttl_seconds=900, path=path):
            return name
    return None


def release_visitor_slot(name: str, owner: str,
                         path: Path | None = None) -> bool:
    return release_lock(name, owner, path=path)


class SpendCap:
    """Thread-safe spend cap for concurrent model calls.

    A call reserves its estimate before dialling and settles the actual
    cost after, so several calls in flight can never push committed spend
    past the cap: when ``reserve`` returns False the caller must not dial.
    """

    def __init__(self, cap_usd: float):
        self.cap_usd = float(cap_usd)
        self._spent = 0.0
        self._reserved = 0.0
        self._refusals = 0
        self._lock = threading.Lock()

    def reserve(self, estimate_usd: float) -> bool:
        """Hold estimate_usd of budget. False when the cap is reached."""
        with self._lock:
            if self._spent + self._reserved + estimate_usd > self.cap_usd:
                self._refusals += 1
                return False
            self._reserved += estimate_usd
            return True

    def settle(self, estimate_usd: float, actual_usd: float) -> None:
        """Release a reservation and commit the actual cost instead."""
        with self._lock:
            self._reserved = max(self._reserved - estimate_usd, 0.0)
            self._spent += max(actual_usd, 0.0)

    def try_spend(self, actual_usd: float) -> bool:
        """Commit a cost with no reservation step. False past the cap."""
        with self._lock:
            if self._spent + actual_usd > self.cap_usd:
                self._refusals += 1
                return False
            self._spent += actual_usd
            return True

    @property
    def spent_usd(self) -> float:
        """Committed spend so far."""
        with self._lock:
            return self._spent

    @property
    def refusals(self) -> int:
        """Calls refused for lack of budget."""
        with self._lock:
            return self._refusals


def call_with_cap(respond_fn, cap: SpendCap, estimate_usd: float,
                  *args, **kwargs) -> dict:
    """Dial once through a SpendCap: reserve, call, settle actual cost.

    Returns the model result with ``capped`` True; when the cap is hit,
    nothing is dialled and the result carries ``capped`` False plus the
    refusal reason.
    """
    if not cap.reserve(estimate_usd):
        return {"output": [], "text": "",
                "error": "spend cap reached: call refused before dialling",
                "usage": {}, "capped": False}
    result = respond_fn(*args, **kwargs)
    try:
        inputs, cached, outputs = usage_of(result)
        actual = cost_usd(inputs, cached, outputs)
    except (TypeError, ValueError, KeyError):
        actual = estimate_usd
    cap.settle(estimate_usd, actual)
    result["capped"] = True
    return result
