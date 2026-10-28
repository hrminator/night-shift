"""Matched replay experiment: replay vs re-sent documents (live model calls).

Takes the recorded hero job (RECORDED_JOB) at its paused state (after the
question, before the answer) and forks it in throwaway DATA_DIRs with the
same owner answer at the same virtual time, 3 runs per arm:

- arm "replay": resumes exactly as the app does (``runner.resume_job``:
  encrypted reasoning items replayed, documents not re-sent);
- arm "resend": resumes with the reasoning items dropped and the source
  documents re-attached as input (the read-turn plus reassess-turn source
  content: both PDFs by fresh file id plus the portal/terms/venue/studio
  texts), via ``resume_with_resend`` below, which mirrors ``resume_job``
  step by step except for those two changes.

Per run records input/cached/output tokens, seconds, cost, whether the
hold passed the gateway, drafts proposed during the resume, and whether
any draft thanks the venue for confirming. Writes
results/replay-matched-<timestamp>/results.json + report.md.

Usage:
  RECORDED_JOB=6c7c7c742513 uv run python scripts/replay_matched.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from app import replay as replay_mod  # noqa: E402
from app import runner  # noqa: E402
from app.adapter import MODEL, drop_reasoning_items  # noqa: E402
from app.adapter import respond as real_respond  # noqa: E402
from app.spend import cost_usd, usage_of  # noqa: E402
from app.store import list_events  # noqa: E402

REPS = 3
ARMS = ("replay", "resend")


def thanks_venue(body: object) -> bool:
    """True when a draft thanks the venue for confirming receipt."""
    text = str(body or "").lower()
    return "thank" in text and (
        "confirm" in text or "venue" in text or "sjosalen" in text
        or "sjøsalen" in text)


def load_recorded() -> dict:
    """The recorded job, its paused state, and its own answer to reuse."""
    resolved = replay_mod.resolve_recorded_job()
    if resolved is None:
        raise SystemExit("no recorded job found (set RECORDED_JOB)")
    record = resolved["record"]
    events = list(record.get("events") or [])
    if not any(e.get("kind") == "checkpoint" for e in events):
        raise SystemExit("recorded job has no checkpoint to fork from")
    answers = [e for e in events if e.get("kind") == "owner_answer"]
    if answers:
        choice = str((answers[0].get("payload") or {}).get("choice", ""))
        at = str(answers[0].get("virtual_time") or "01:05")
    else:
        choice, at = "Bergen: the venue can receive it", "01:05"
    handoffs = [e for e in events if e.get("kind") == "handoff"]
    variant = ((handoffs[0].get("payload") or {}).get("variant", "hero")
               if handoffs else "hero")
    return {"job_id": resolved["job_id"], "record": record,
            "choice": choice, "answer_vt": at, "variant": variant}


def fork_job(record: dict, choice: str, answer_vt: str,
             data_dir: Path) -> str:
    """Copy the paused night into a throwaway DATA_DIR; file the answer."""
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DATA_DIR"] = str(data_dir)
    return replay_mod.copy_job_for_visitor(
        record, choice, answer_virtual_time=answer_vt)


def resume_with_resend(
    job_id: str,
    respond_fn: Callable[..., dict],
    upload_fn: Callable[[Path], dict] | None = None,
    delete_fn: Callable[[str], None] | None = None,
    arm: str = "supervision",
) -> dict:
    """Resume like ``runner.resume_job`` but re-sending the documents.

    Same checkpoint input minus the encrypted reasoning items, plus one
    user message carrying the read-turn and reassess-turn source content
    (both PDFs by fresh file id, texts inline). Uploads are deleted after
    the resume; the files endpoint keeps no expiry.
    """
    from app.store import get_job as _get_job
    from app.store import set_job_status as _set_status

    job = _get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "refused",
                "reason": "unknown job"}
    if job.get("status") != "answered":
        return {"job_id": job_id, "status": "refused",
                "reason": "resume needs status answered, has "
                f"{job.get('status')}"}
    checkpoints = [e for e in list_events(job_id)
                   if e["kind"] == "checkpoint"]
    if not checkpoints:
        return {"job_id": job_id, "status": "refused",
                "reason": "no checkpoint to resume from"}
    saved_input = copy.deepcopy(
        list((checkpoints[-1]["payload"] or {}).get("next_input", [])))
    for entry in saved_input:
        content = entry.get("content")
        if entry.get("type") == "message" and isinstance(content, list):
            entry["content"] = [part for part in content
                                if part.get("type") != "input_file"]
    saved_input = drop_reasoning_items(saved_input)
    ask_call_id = next(
        (entry.get("call_id") for entry in saved_input
         if entry.get("type") == "function_call"
         and entry.get("name") == "ask_owner"), None)
    if ask_call_id is None:
        return {"job_id": job_id, "status": "refused",
                "reason": "checkpoint has no pending ask_owner call"}
    answers = [e for e in list_events(job_id)
               if e["kind"] == "owner_answer"]
    answer = answers[-1]
    answer_vt = answer["virtual_time"]
    resume_input = saved_input + [{
        "type": "message",
        "role": "user",
        "content": "The owner answered your question (ask_owner call "
        f"{ask_call_id}) with: \"{(answer['payload'] or {}).get('choice', '')}\""
        f" (owner_answer event {answer['id']}, source owner, at {answer_vt}"
        " virtual time). This is information only; authority for the hold"
        " comes from the brief's standing permission.",
    }]
    stale_message = runner.build_resume_stale_message(job_id)
    if stale_message is not None:
        resume_input = resume_input + [{
            "type": "message", "role": "user", "content": stale_message,
        }]
    upload = upload_fn or runner.upload_pdf
    delete = delete_fn or runner.delete_file
    handoffs = [e for e in list_events(job_id) if e["kind"] == "handoff"]
    variant = ((handoffs[0].get("payload") or {}).get("variant", "hero")
               if handoffs else "hero")
    original_meta = upload(runner.ORIGINAL_PDF)
    revised_meta = upload(runner.REVISED_PDF)
    try:
        resume_input = resume_input + [{
            "type": "message",
            "role": "user",
            "content": runner.build_read_content(
                original_meta["id"], variant)
            + runner.build_reassess_content(revised_meta["id"], variant),
        }]
        _set_status(job_id, status="resuming", current_step="resuming",
                    virtual_time=answer_vt)
        turn = runner.run_turn(
            job_id, runner.build_resume_instructions(job_id, answer, arm),
            resume_input, runner.RESUME_TOOLS, respond_fn, answer_vt,
            arm=arm, call_type="resume",
            executor=runner.execute_resume_tool_call,
        )
    finally:
        for meta in (original_meta, revised_meta):
            try:
                delete(meta["id"])
            except Exception:  # noqa: BLE001 - cleanup never fails a run
                pass
    if turn["status"] == "failed":
        return {"job_id": job_id, "status": "failed",
                "result": turn["result"]}
    _set_status(job_id, status="done", current_step="done",
                virtual_time=runner.VT_MORNING)
    return {"job_id": job_id, "status": "done", "result": turn["result"]}


def run_once(arm: str, recorded: dict, rep: int, out_dir: Path) -> dict:
    """One forked resume in a throwaway DATA_DIR with usage capture."""
    run_dir = out_dir / f"run-{arm}-{rep}"
    data_dir = run_dir / "data"
    run_dir.mkdir(parents=True, exist_ok=True)
    calls: list[dict] = []

    def wrapped(instructions, input_items, **kwargs):
        result = real_respond(instructions, input_items, **kwargs)
        inputs, cached, outputs = usage_of(result)
        calls.append({"call_type": kwargs.get("call_type", "?"),
                      "input_tokens": inputs, "cached_tokens": cached,
                      "output_tokens": outputs,
                      "usd": cost_usd(inputs, cached, outputs),
                      "seconds": result.get("seconds", 0.0),
                      "model": result.get("model"),
                      "status": result.get("status")})
        return result

    wall_start = time.time()
    job_id = fork_job(recorded["record"], recorded["choice"],
                      recorded["answer_vt"], data_dir)
    if arm == "replay":
        summary = runner.resume_job(job_id, respond_fn=wrapped)
    else:
        summary = resume_with_resend(job_id, respond_fn=wrapped)
    wall = round(time.time() - wall_start, 1)
    events = list_events(job_id)
    answers = [e for e in events if e["kind"] == "owner_answer"]
    answer_id = answers[-1]["id"] if answers else 0
    new_drafts = [e for e in events
                  if e["kind"] == "draft" and e["id"] > answer_id]
    thanked = sum(1 for draft in new_drafts
                  if thanks_venue((draft.get("payload") or {}).get("body")))
    export_path = run_dir / f"job-{arm}-{rep}.json"
    runner.export_job(job_id, export_path)
    record = {
        "arm": arm, "rep": rep, "job_id": job_id,
        "status": summary["status"],
        "answer": recorded["choice"], "answer_vt": recorded["answer_vt"],
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "cached_tokens": sum(c["cached_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "seconds": round(sum(c["seconds"] for c in calls), 1),
        "usd": round(sum(c["usd"] for c in calls), 4),
        "model_calls": len(calls),
        "hold_passed_gateway": any(e["kind"] == "effect" for e in events),
        "drafts": len(new_drafts),
        "thanks_venue_runs": 1 if thanked else 0,
        "thanks_venue_drafts": thanked,
        "wall_seconds": wall,
        "export": str(export_path),
        "calls": calls,
    }
    print(f"[{arm}/{rep}] job={job_id} status={summary['status']}"
          f" in={record['input_tokens']} cached={record['cached_tokens']}"
          f" out={record['output_tokens']} hold={record['hold_passed_gateway']}"
          f" drafts={record['drafts']} thanks={thanked}"
          f" usd={record['usd']} s={record['seconds']} wall={wall}",
          flush=True)
    return record


def means(records: list[dict]) -> dict:
    """Mean input/cached/output tokens, seconds and cost per arm."""
    count = len(records) or 1
    return {
        "runs": len(records),
        "mean_input_tokens": round(
            sum(r["input_tokens"] for r in records) / count, 1),
        "mean_cached_tokens": round(
            sum(r["cached_tokens"] for r in records) / count, 1),
        "mean_output_tokens": round(
            sum(r["output_tokens"] for r in records) / count, 1),
        "mean_seconds": round(
            sum(r["seconds"] for r in records) / count, 1),
        "mean_usd": round(sum(r["usd"] for r in records) / count, 4),
        "holds_passed": sum(1 for r in records
                            if r["hold_passed_gateway"]),
        "mean_drafts": round(
            sum(r["drafts"] for r in records) / count, 2),
        "thanks_venue_runs": sum(r["thanks_venue_runs"] for r in records),
        "job_ids": [r["job_id"] for r in records],
    }


def render_report(payload: dict) -> str:
    """Markdown report with means per arm and the job ids."""
    lines = [
        "# Matched replay experiment — DEVELOPMENT RUN",
        "",
        f"Recorded night: {payload['recorded_job_id']} at its paused state"
        f" (after the question, before the answer); same owner answer"
        f" {payload['answer']!r} at {payload['answer_vt']} in every fork.",
        f"Arm replay resumes exactly as the app does (encrypted reasoning"
        f" replayed, documents not re-sent); arm resend drops the reasoning"
        f" items and re-attaches the read-turn plus reassess-turn source"
        f" content (both PDFs by fresh file id, texts inline).",
        f"Model: {payload['model']} · effort: {payload['effort']} ·"
        f" started: {payload['started_utc']}",
        "",
        "## Means per arm (3 runs each)",
        "",
        "| arm | mean input | mean cached | mean output | mean s |"
        " mean $ | holds | mean drafts | thanks-venue runs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ARMS:
        stats = payload["means"][arm]
        lines.append(
            f"| {arm} | {stats['mean_input_tokens']} |"
            f" {stats['mean_cached_tokens']} | {stats['mean_output_tokens']} |"
            f" {stats['mean_seconds']} | {stats['mean_usd']} |"
            f" {stats['holds_passed']}/{stats['runs']} |"
            f" {stats['mean_drafts']} |"
            f" {stats['thanks_venue_runs']}/{stats['runs']} |")
    lines += ["",
              "## Runs",
              "",
              "| arm | rep | job | status | in | cached | out | hold |"
              " drafts | thanks | usd | s |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for record in payload["records"]:
        lines.append(
            f"| {record['arm']} | {record['rep']} | {record['job_id']} |"
            f" {record['status']} | {record['input_tokens']} |"
            f" {record['cached_tokens']} | {record['output_tokens']} |"
            f" {record['hold_passed_gateway']} | {record['drafts']} |"
            f" {record['thanks_venue_drafts']} | {record['usd']} |"
            f" {record['seconds']} |")
    lines += ["",
              "Every run above is a development run.",
              ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    recorded = load_recorded()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("results") / f"replay-matched-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    records = []
    try:
        for arm in ARMS:
            for rep in (1, 2, 3):
                records.append(run_once(arm, recorded, rep, out_dir))
    finally:
        payload = {
            "development_run": True,
            "experiment": "replay-vs-resend",
            "recorded_job_id": recorded["job_id"],
            "answer": recorded["choice"],
            "answer_vt": recorded["answer_vt"],
            "model": MODEL,
            "effort": runner.EFFORT,
            "started_utc": started.isoformat(timespec="seconds"),
            "records": records,
            "means": {arm: means([r for r in records if r["arm"] == arm])
                      for arm in ARMS},
        }
        (out_dir / "results.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        (out_dir / "report.md").write_text(render_report(payload),
                                           encoding="utf-8")
        print(f"WROTE {out_dir / 'results.json'}")
        print(f"WROTE {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
