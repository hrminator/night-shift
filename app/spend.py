"""Model spend accounting and live-resume guards.

Spend is computed from token counts with the Spark 1.3 prices ($1.25 input,
$0.15 cached input, $4.25 output per million) and stored per UTC day in the
database. A visitor resume is refused when the day's total has reached the
cap (DAILY_CAP_USD, default $5), or when 2 live resumes already run.
"""

from __future__ import annotations

import os
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
