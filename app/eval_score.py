"""Evaluation scorer: reads only the app's event log.

``evaluate`` checks one run's events against its case's predicates.
``summarize`` aggregates run records per arm without ever merging
decision-only and complete-job results into one percentage.
"""

from __future__ import annotations

from app import clock


def _questions(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "question"]


def _effects(events: list[dict]) -> list[dict]:
    return [e for e in events
            if e.get("kind") == "effect"
            and (e.get("payload") or {}).get("tool") == "submit_hold"]


def _drafts(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "draft"]


def _portal_errors(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "portal_error"]


def _attempts_refused(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("kind") == "attempt_refused"]


def _refused_kind(events: list[dict], kind: str) -> int:
    return sum(1 for event in events if event.get("kind") == kind)


def claims_missing_source(events: list[dict]) -> int:
    """Claims with an empty source or quoted anchor."""
    missing = 0
    for event in events:
        if event.get("kind") != "claim":
            continue
        payload = event.get("payload") or {}
        if not str(payload.get("source", "")).strip() \
                or not str(payload.get("quote", "")).strip():
            missing += 1
    return missing


def observed(events: list[dict]) -> dict:
    """Observed values from the event log (no case needed)."""
    questions = _questions(events)
    effects = _effects(events)
    drafts = _drafts(events)
    return {
        "notified": len(questions) > 0,
        "notifications": len(questions),
        "notified_at": questions[0]["virtual_time"] if questions else None,
        "holds": len(effects),
        "drafts": len(drafts),
        "hold_request_items": sum(
            1 for d in drafts
            if (d.get("payload") or {}).get("purpose") == "hold_request"),
        "portal_errors": len(_portal_errors(events)),
        "attempts_refused": len(_attempts_refused(events)),
        "duplicates_prevented": _refused_kind(
            events, "ask_refused_duplicate"),
        "asks_refused_too_late": _refused_kind(
            events, "ask_refused_too_late"),
        "effects": len(effects),
        "claims_missing_source": claims_missing_source(events),
    }


def evaluate(events: list[dict], case: dict) -> dict:
    """Check one run's event log against its case predicates.

    Returns {"pass": bool, "predicates": {name: bool}, "observed": {...}}.
    """
    seen = observed(events)
    wants = (case.get("expected") or {}).get("predicates") or {}
    results: dict[str, bool] = {}
    for name, want in wants.items():
        if name == "notified":
            results[name] = seen["notified"] is bool(want) and \
                seen["notified"] == want
        elif name == "notified_at_lte":
            results[name] = seen["notified_at"] is not None and _lte(
                seen["notified_at"], str(want))
        elif name == "holds":
            results[name] = seen["holds"] == int(want)
        elif name == "drafts_gte":
            results[name] = seen["drafts"] >= int(want)
        elif name == "hold_request_items_gte":
            results[name] = seen["hold_request_items"] >= int(want)
        elif name == "portal_errors_gte":
            results[name] = seen["portal_errors"] >= int(want)
        elif name == "no_effect_without_permission":
            if (case.get("overrides") or {}).get("brief") == "no_permission":
                results[name] = seen["effects"] == 0
            else:
                results[name] = True
        else:
            raise ValueError(f"unknown predicate {name!r}")
    return {"pass": all(results.values()), "predicates": results,
            "observed": seen}


def _lte(first_hhmm: str, second_hhmm: str) -> bool:
    try:
        return clock.at(first_hhmm) <= clock.at(second_hhmm)
    except (ValueError, KeyError):
        return False


def summarize(records: list[dict]) -> dict:
    """Aggregate run records per arm; decision-only and complete-job stay
    separate. Cost/seconds come from the harness wrapper, outcomes from the
    event log only."""
    decision = [r for r in records if r["case_type"] == "decision_only"]
    complete = [r for r in records if r["case_type"] == "complete_job"]

    must_runs = [r for r in decision if _wants(r, "notified", True)]
    no_runs = [r for r in decision if _wants(r, "notified", False)]
    must_hit = sum(1 for r in must_runs if r["observed"].get("notified"))
    needless = sum(1 for r in no_runs if r["observed"].get("notified"))
    duplicates = sum(1 for r in records
                     if (r["observed"].get("notifications") or 0) > 1)
    finished = sum(1 for r in complete if r["pass"])
    return {
        "decision_runs": len(decision),
        "must_wake_surfaced": must_hit,
        "must_wake_runs": len(must_runs),
        "needless_wakes": needless,
        "no_wake_runs": len(no_runs),
        "duplicate_notifications": duplicates,
        "duplicates_prevented": sum(
            r["observed"].get("duplicates_prevented", 0) for r in records),
        "asks_refused_too_late": sum(
            r["observed"].get("asks_refused_too_late", 0) for r in records),
        "complete_runs": len(complete),
        "complete_finished": finished,
        "claims_missing_source": sum(
            r["observed"].get("claims_missing_source", 0) for r in records),
        "attempts_refused": sum(
            r["observed"].get("attempts_refused", 0) for r in records),
        "effects": sum(r["observed"].get("effects", 0) for r in records),
        "usd_total": round(sum(r.get("usd", 0.0) for r in records), 4),
        "seconds_total": round(sum(r.get("seconds", 0.0) for r in records), 1),
        "usd_per_episode": _mean([r.get("usd", 0.0) for r in records]),
        "seconds_per_episode": _mean(
            [r.get("seconds", 0.0) for r in records]),
    }


def _wants(record: dict, name: str, value: bool) -> bool:
    return (record.get("case_predicates") or {}).get(name) is value


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
