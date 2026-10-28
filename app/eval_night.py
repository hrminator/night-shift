"""Run one evaluation case as a fresh night in a throwaway DATA_DIR.

The flow mirrors ``run_job`` (read turn, revised-quote event, reassess
turn, optional answer plus resume) but honours the case overrides: venue
variant, permission-less brief, fixture replacements, revised event time,
alternate revised PDF, owner answer time and one-shot portal outage.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from app import eval_world
from app import permission as _permission
from app import runner
from app.store import append_event, clear_thread_data_dir, create_job, init_db, list_events, set_job_status, set_thread_data_dir


def run_case(
    case: dict,
    arm: str,
    respond_fn: Callable[..., dict],
    data_dir: Path,
    work_dir: Path,
    out_path: Path,
    upload_fn: Callable[[Path], dict] | None = None,
    delete_fn: Callable[[str], None] | None = None,
) -> dict:
    """Run one case night; export the job; return run details."""
    if arm not in ("supervision", "direct"):
        raise ValueError(f"unknown arm {arm!r}")
    set_thread_data_dir(data_dir)
    previous_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(data_dir)
    try:
        return _run_case(case, arm, respond_fn, work_dir, out_path,
                         upload_fn or runner.upload_pdf,
                         delete_fn or runner.delete_file)
    finally:
        clear_thread_data_dir()
        if previous_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = previous_data_dir


def _run_case(case, arm, respond_fn, work_dir, out_path, upload_fn,
              delete_fn) -> dict:
    from app import portal as _portal

    overrides = case.get("overrides") or {}
    variant = overrides.get("venue", "hero")
    revised_time = overrides.get("revised_time", "00:38")
    init_db()
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    job = create_job(status="running", current_step="read_turn",
                     virtual_time=runner.VT_HANDOFF)
    job_id = job["id"]
    handoff: dict = {"brief": "fixtures/brief.md", "source": "owner",
                     "variant": variant, "arm": arm,
                     "case": case.get("id")}
    if overrides.get("brief") == "no_permission":
        handoff["brief_text"] = eval_world.NO_PERMISSION_BRIEF
    append_event(job_id, runner.VT_HANDOFF, "handoff", handoff)
    _permission.ensure_permission_record(job_id, runner.VT_HANDOFF)

    original_meta = upload_fn(runner.ORIGINAL_PDF)
    revised_meta = upload_fn(eval_world.revised_pdf_path(case, work_dir))
    portal_restore = None
    if overrides.get("portal") == "error_once":
        portal_restore = _arm_portal_once(_portal)
    try:
        with eval_world.patched(case):
            read_first = [{"type": "message", "role": "user",
                           "content": runner.build_read_content(
                               original_meta["id"], variant)}]
            read_turn = runner.run_turn(
                job_id, runner.build_read_instructions(), read_first,
                runner.READ_TOOLS, respond_fn, runner.VT_READ, arm=arm,
                call_type="read")
            if read_turn["status"] == "failed":
                return _finish(job_id, out_path, "failed",
                               note="read turn failed")
            append_event(job_id, revised_time, "revised_quote",
                         {"quote": "Q-1187-B", "replaces": "Q-1187",
                          "detail": "Baltic Print revised quote Q-1187-B"
                          " arrives and replaces original quote Q-1187"})
            reassess_first = list(read_turn["input"]) + [
                {"type": "message", "role": "user",
                 "content": runner.build_reassess_content(
                     revised_meta["id"], variant,
                     event_time=revised_time)}]
            reassess = runner.run_turn(
                job_id, runner.build_reassess_instructions(arm),
                reassess_first, runner.REASSESS_TOOLS, respond_fn,
                revised_time, arm=arm, call_type="reassess")
            if reassess["status"] == "failed":
                return _finish(job_id, out_path, "failed",
                               note="reassess turn failed")
            runner.maybe_ground_scan_line(
                job_id, respond_fn=respond_fn, virtual_time=revised_time)
            asked = runner.question_event_id_of(job_id)
            if asked is not None:
                runner.save_checkpoint(job_id, reassess["input"], asked)
                status = "waiting_for_owner"
            elif [e for e in list_events(job_id)
                  if e["kind"] == "effect"]:
                set_job_status(job_id, status="done", current_step="done",
                               virtual_time=runner.VT_MORNING)
                status = "done"
            else:
                set_job_status(job_id, status="decision_done",
                               current_step="decision_done",
                               virtual_time=runner.VT_DECISION)
                status = "decision_done"
            answer_spec = overrides.get("owner_answer")
            if case.get("type") == "complete_job" and answer_spec \
                    and status == "waiting_for_owner":
                runner.store_answer(job_id, answer_spec["choice"],
                                    answer_spec.get("time", "01:05"))
                resumed = runner.resume_job(job_id, respond_fn=respond_fn,
                                            arm=arm)
                status = resumed["status"]
            return _finish(job_id, out_path, status)
    finally:
        if portal_restore is not None:
            portal_restore()
        for meta in (original_meta, revised_meta):
            try:
                delete_fn(meta["id"])
            except Exception:  # noqa: BLE001 - cleanup never fails a run
                pass


def _arm_portal_once(portal_mod):
    """Fail the next ensure_hold with a simulated outage, then restore."""
    original = portal_mod.ensure_hold
    state = {"failed": False}

    def flaky(*args, **kwargs):
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("simulated portal outage")
        return original(*args, **kwargs)

    portal_mod.ensure_hold = flaky  # type: ignore[method-assign]

    def restore():
        portal_mod.ensure_hold = original  # type: ignore[method-assign]

    return restore


def _finish(job_id: str, out_path: Path, status: str,
            note: str = "") -> dict:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    runner.export_job(job_id, target)
    record: dict = {"job_id": job_id, "status": status,
                    "export": str(target)}
    if note:
        record["note"] = note
    return record
