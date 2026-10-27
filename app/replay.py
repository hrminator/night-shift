"""Recorded hero runs and visitor copies.

The front door replays one recorded hero run from its exported events. A
visitor answer copies that run's events up to and including the checkpoint
into the live database under a NEW job id: the recorded export is never
modified, no operations rows are copied (operation ids derive from the new
job id, so the copy gets its own), and the copy's outbox starts empty
(post-checkpoint drafts and deliveries stay behind).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

RECORDED_ENV_VAR = "RECORDED_JOB"


def runs_dirs() -> list[Path]:
    """Live runs first, then the records baked into the image."""
    from app.main import bundled_runs_dir, data_dir
    live = data_dir() / "runs"
    bundled = bundled_runs_dir()
    dirs = [live]
    try:
        same = live.resolve() == bundled.resolve()
    except OSError:
        same = False
    if not same:
        dirs.append(bundled)
    return dirs


def _export_files() -> list[Path]:
    files: list[Path] = []
    for directory in runs_dirs():
        if directory.is_dir():
            files.extend(sorted(directory.glob("job-*.json")))
    return files


def find_run_file(name: str) -> Path | None:
    """Find one run export by job id, file name, or file stem.

    Looks in the live DATA_DIR/runs first, then falls back to the records
    baked into the image under data/runs, so the recorded replay works even
    when the mounted volume does not hold the file yet.
    """
    for directory in runs_dirs():
        for candidate in (directory / f"job-{name}.json",
                          directory / name,
                          directory / f"{name}.json"):
            if candidate.is_file():
                return candidate
    return None


def _is_hero_with_wake_and_hold(record: dict) -> bool:
    try:
        events = record["events"]
    except (KeyError, TypeError):
        return False
    handoffs = [e for e in events if e.get("kind") == "handoff"]
    if not handoffs or (handoffs[0].get("payload") or {}).get(
            "variant") != "hero":
        return False
    if not any(e.get("kind") == "decision" and (e.get("payload") or {}).get(
            "outcome") == "wake" for e in events):
        return False
    return any(e.get("kind") == "effect" for e in events)


def _recorded_date(record: dict, path: Path) -> str:
    try:
        first = (record.get("events") or [])[0]
        stamp = str(first.get("created_at") or "")[:10]
        if stamp:
            return stamp
    except (IndexError, AttributeError):
        pass
    try:
        import datetime
        return datetime.datetime.fromtimestamp(
            path.stat().st_mtime, datetime.timezone.utc).date().isoformat()
    except OSError:
        return "unknown date"


def _load_record(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def resolve_recorded_job() -> dict | None:
    """Pick the replay source: RECORDED_JOB, else the latest hero run.

    RECORDED_JOB may be a job id, a file name, or a path. The default is
    the latest successful hero job with a wake and a hold, newest first by
    event time, then file time. Returns {"job_id", "record", "path",
    "date"} or None.
    """
    want = (os.environ.get(RECORDED_ENV_VAR) or "").strip()
    if want:
        candidate = find_run_file(want)
        if candidate is not None:
            record = _load_record(candidate)
            if record is not None:
                job_id = str(record.get("job_id") or candidate.stem
                             .removeprefix("job-"))
                return {"job_id": job_id, "record": record,
                        "path": candidate,
                        "date": _recorded_date(record, candidate)}
        direct = Path(want)
        if direct.is_file():
            record = _load_record(direct)
            if record is not None:
                job_id = str(record.get("job_id") or direct.stem
                             .removeprefix("job-"))
                return {"job_id": job_id, "record": record, "path": direct,
                        "date": _recorded_date(record, direct)}
        return None
    best: dict | None = None
    best_key: tuple = ()
    for path in _export_files():
        record = _load_record(path)
        if record is None or not _is_hero_with_wake_and_hold(record):
            continue
        stamps = [str(e.get("created_at") or "")
                  for e in record.get("events", [])]
        key = (max(stamps) if stamps else "", path.stat().st_mtime)
        if best is None or key > best_key:
            best, best_key = path, key
    if best is None:
        return None
    record = _load_record(best)
    assert record is not None
    job_id = str(record.get("job_id") or best.stem.removeprefix("job-"))
    return {"job_id": job_id, "record": record, "path": best,
            "date": _recorded_date(record, best)}


def replay_events(record: dict) -> list[dict]:
    """Events from 21:30 up to and including the checkpoint."""
    events = list(record.get("events") or [])
    checkpoints = [e for e in events if e.get("kind") == "checkpoint"]
    if not checkpoints:
        return events
    stop = max(int(e.get("id", 0)) for e in checkpoints)
    return [e for e in events if int(e.get("id", 0)) <= stop]


def copy_job_for_visitor(record: dict, choice: str,
                         answer_virtual_time: str = "01:05") -> str:
    """Copy a recorded run into a new live job and file the visitor answer.

    Copies kinds in stored order up to and including the checkpoint with
    fresh event ids; remaps the checkpoint's question pointer to the new
    question id. Historical evidence lists keep the recorded run's ids
    (display only; the gateway cites live answer and portal ids). Then the
    visitor's choice is stored as owner_answer, exactly like the owner's.
    """
    from app import runner as runner_mod
    from app.store import append_event, create_job, set_job_status

    source = replay_events(record)
    if not any(e.get("kind") == "checkpoint" for e in source):
        raise ValueError("recorded job has no checkpoint to resume from")
    job = create_job(status="running", current_step="waiting_for_owner",
                     virtual_time="00:47")
    new_id = job["id"]
    old_to_new: dict[int, int] = {}
    for event in source:
        payload = copy.deepcopy(event.get("payload") or {})
        if (event.get("kind") == "checkpoint" and isinstance(
                payload.get("question_event_id"), int)):
            # Events are append-only, so the pointer is remapped on the
            # way in, never edited afterwards.
            payload["question_event_id"] = old_to_new.get(
                int(payload["question_event_id"]),
                payload["question_event_id"])
            payload["copied_from_recorded"] = True
        stored = append_event(new_id, event.get("virtual_time") or "00:47",
                              event.get("kind") or "note", payload)
        old_to_new[int(event.get("id", 0))] = int(stored["id"])
    from app.store import list_events
    live_questions = [e for e in list_events(new_id)
                      if e["kind"] == "question"]
    set_job_status(new_id, status="waiting_for_owner",
                   pending_question_id=(
                       live_questions[-1]["id"] if live_questions else None),
                   current_step="waiting_for_owner", virtual_time="00:47")
    # store_answer keys off DATA_DIR like every other store call.
    runner_mod.store_answer(new_id, choice,
                            virtual_time=answer_virtual_time)
    return new_id
