"""Evaluation harness: run cases as fresh nights, score the event log.

Runs each case N times as a fresh night in a throwaway DATA_DIR per run,
exports every job, and writes results.json plus report.md. Every run is
marked a development run. Nights run in parallel threads with
``--concurrency N`` (default 2); each thread pins its own throwaway
DATA_DIR, so ``--concurrency 1`` is the sequential path.

Usage:
  uv run python scripts/eval.py --arm supervision --cases all --runs 1
  uv run python scripts/eval.py --arm direct --cases W1_timely_answer --runs 3
  uv run python scripts/eval.py --arm direct --cases all --concurrency 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from app import eval_night, eval_score, eval_world, runner
from app.adapter import MODEL, respond as real_respond
from app.spend import cost_usd, usage_of

_PRINT_LOCK = threading.Lock()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True,
                        choices=["supervision", "direct"])
    parser.add_argument("--cases", default="all",
                        help="'all' or comma-separated case ids")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2,
                        help="parallel nights; 1 runs sequentially")
    parser.add_argument("--out", default="",
                        help="output dir; default results/<utc timestamp>/")
    args = parser.parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    return args


def resolve_cases(selection: str) -> list[dict]:
    cases = eval_world.list_cases()
    if selection == "all":
        return cases
    wanted = [part.strip() for part in selection.split(",") if part.strip()]
    by_id = {case["id"]: case for case in cases}
    unknown = [name for name in wanted if name not in by_id]
    if unknown:
        raise SystemExit(f"unknown cases: {unknown}")
    return [by_id[name] for name in wanted]


def run_all(arm: str, cases: list[dict], runs: int, out_dir: Path,
            concurrency: int = 2) -> dict:
    """Run every case N times; write results.json + report.md."""
    started = datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(case, run, episode)
             for episode, (case, run) in enumerate(
                 ((case, run) for case in cases
                  for run in range(1, runs + 1)), start=1)]
    harness_start = time.time()
    if concurrency == 1:
        records = [run_once(arm, case, run, out_dir, episode)
                   for case, run, episode in tasks]
    else:
        with ThreadPoolExecutor(max_workers=concurrency,
                                thread_name_prefix="night") as pool:
            futures = [pool.submit(run_once, arm, case, run, out_dir,
                                   episode)
                       for case, run, episode in tasks]
            records = [future.result() for future in futures]
    records.sort(key=lambda record: record["episode"])
    elapsed = time.time() - harness_start
    wall_sum = round(sum(record.get("wall_seconds", 0.0)
                         for record in records), 1)
    summary = eval_score.summarize(records)
    payload = {
        "development_run": True,
        "arm": arm,
        "model": MODEL,
        "effort": runner.EFFORT,
        "cases": [case["id"] for case in cases],
        "runs_per_case": runs,
        "concurrency": concurrency,
        "started_utc": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "wall_sum_seconds": wall_sum,
        "records": records,
        "summary": summary,
    }
    (out_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (out_dir / "report.md").write_text(
        render_report(payload), encoding="utf-8")
    return payload


def run_once(arm: str, case: dict, run: int, out_dir: Path,
             episode: int) -> dict:
    """One episode: fresh DATA_DIR, real model calls, exported job."""
    case_dir = out_dir / f"run-{case['id']}-{run}"
    data_dir = case_dir / "data"
    work_dir = case_dir / "work"
    case_dir.mkdir(parents=True, exist_ok=True)
    calls: list[dict] = []
    wall_start = time.time()

    def wrapped(instructions, input_items, **kwargs):
        result = real_respond(instructions, input_items, **kwargs)
        inputs, cached, outputs = usage_of(result)
        calls.append({"input_tokens": inputs, "cached_tokens": cached,
                      "output_tokens": outputs,
                      "usd": cost_usd(inputs, cached, outputs),
                      "seconds": result.get("seconds", 0.0),
                      "model": result.get("model"),
                      "status": result.get("status")})
        return result

    record: dict = {
        "development_run": True,
        "arm": arm,
        "case": case["id"],
        "case_type": case["type"],
        "case_predicates": (case.get("expected") or {}).get(
            "predicates") or {},
        "run": run,
        "episode": episode,
    }
    try:
        night = eval_night.run_case(
            case, arm, wrapped, data_dir, work_dir,
            case_dir / f"job-{case['id']}-{run}.json")
        exported = json.loads(Path(night["export"]).read_text(encoding="utf-8"))
        events = exported["events"]
        scored = eval_score.evaluate(events, case)
        record.update({
            "job_id": night["job_id"],
            "status": night["status"],
            "export": night["export"],
            "pass": scored["pass"],
            "predicates": scored["predicates"],
            "observed": scored["observed"],
            "decision_reason": decision_first_sentence(events),
        })
        if night["status"] not in ("done", "waiting_for_owner",
                                   "decision_done"):
            record["pass"] = False
            record["note"] = night.get("note", night["status"])
    except Exception as exc:  # noqa: BLE001 - one bad episode never kills a run
        record.update({
            "status": "error",
            "pass": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
            "observed": {},
            "decision_reason": "—",
        })
    record["calls"] = calls
    record["usd"] = round(sum(call["usd"] for call in calls), 4)
    record["seconds"] = round(sum(call["seconds"] for call in calls), 1)
    record["wall_seconds"] = round(time.time() - wall_start, 1)
    with _PRINT_LOCK:
        print(f"[{arm}/{case['id']}/{run}] status={record.get('status')}"
              f" pass={record.get('pass')} usd={record['usd']}"
              f" s={record['seconds']} wall={record['wall_seconds']}",
              flush=True)
    return record


def first_sentence(text: str, limit: int = 240) -> str:
    """One sentence: up to the first sentence end, whitespace folded."""
    snippet = re.split(r"(?<=[.!?])\s+", (text or "").strip(),
                       maxsplit=1)[0]
    snippet = " ".join(snippet.split())
    if len(snippet) > limit:
        return snippet[:limit].rstrip() + "…"
    return snippet


def decision_first_sentence(events: list[dict]) -> str:
    """First sentence of the night's last recorded decision reason."""
    decisions = [e for e in events if e.get("kind") == "decision"]
    if not decisions:
        return "—"
    reason = str((decisions[-1].get("payload") or {}).get("reason", ""))
    return first_sentence(reason) or "—"


def render_report(payload: dict) -> str:
    """Markdown report: decision-only and complete-job stay separate."""
    summary = payload["summary"]
    lines = [
        "# Night Shift evaluation — DEVELOPMENT RUN",
        "",
        f"Arm: {payload['arm']} · model: {payload['model']} · effort:"
        f" {payload['effort']} · started: {payload['started_utc']}",
        f"Cases: {', '.join(payload['cases'])} ·"
        f" runs per case: {payload['runs_per_case']} ·"
        f" concurrency: {payload.get('concurrency', 1)}",
        "",
        "## Decision-only cases (wake pairs)",
        "",
        f"Must-wake surfaced {summary['must_wake_surfaced']} of"
        f" {summary['must_wake_runs']}.",
        f"Needless wakes {summary['needless_wakes']} on"
        f" {summary['no_wake_runs']} no-wake runs.",
        f"Duplicate notifications that still got through (runs with more"
        f" than one question): {summary['duplicate_notifications']}.",
        f"Duplicates prevented by the app (ask_refused_duplicate):"
        f" {summary.get('duplicates_prevented', 0)} (counted separately).",
        "",
        "## Complete-job cases (W1-W4)",
        "",
        f"Finished correctly {summary['complete_finished']} of"
        f" {summary['complete_runs']}.",
        "",
        "Decision-only and complete-job results are never merged into one"
        " percentage.",
        "",
        "## All runs",
        "",
        f"Claims without a source: {summary['claims_missing_source']}.",
        f"Unauthorized attempts (refused): {summary['attempts_refused']};"
        f" executed effects: {summary['effects']} (counted separately).",
        f"Late asks refused (ask_refused_too_late):"
        f" {summary.get('asks_refused_too_late', 0)}.",
        f"Cost: ${summary['usd_total']:.4f} total,"
        f" ${summary['usd_per_episode']:.4f} mean per episode.",
        f"Model seconds: {summary['seconds_total']:.1f} total,"
        f" {summary['seconds_per_episode']:.1f} mean per episode.",
        f"Harness wall: {payload.get('elapsed_seconds', '?')} s for"
        f" {len(payload['records'])} episodes (sum of episode walls"
        f" {payload.get('wall_sum_seconds', '?')} s).",
        "",
        "## Per-case episodes",
        "",
        "| case | run | status | pass | notified | notified_at | holds |"
        " drafts | usd | seconds | wall |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in payload["records"]:
        seen = record.get("observed") or {}
        lines.append(
            f"| {record['case']} | {record['run']} |"
            f" {record.get('status', '?')} | {record.get('pass', '?')} |"
            f" {seen.get('notified', '?')} | {seen.get('notified_at', '?')} |"
            f" {seen.get('holds', '?')} | {seen.get('drafts', '?')} |"
            f" {record.get('usd', '?')} | {record.get('seconds', '?')} |"
            f" {record.get('wall_seconds', '?')} |")
    lines += ["",
              "## Decision reasons (first sentence)",
              ""]
    for record in payload["records"]:
        lines.append(
            f"- {record['case']} run {record['run']}"
            f" ({record.get('status', '?')},"
            f" pass={record.get('pass', '?')}):"
            f" {record.get('decision_reason', '—')}")
    lines += ["",
              "Every run above is a development run.",
              ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = resolve_cases(args.cases)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) if args.out else Path("results") / stamp
    payload = run_all(args.arm, cases, args.runs, out_dir,
                      concurrency=args.concurrency)
    print(f"WROTE {out_dir / 'results.json'}")
    print(f"WROTE {out_dir / 'report.md'}")
    print(json.dumps(payload["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
