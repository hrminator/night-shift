"""Probe the B1 grounding call: locate the arrival line 10 times.

Runs locate_line against fixtures/baltic_quote_Q-1187-B.png with the
revised arrival line's exact text from lines.json, scores each box
against the band (vertical centre inside the band AND at least 70% of
the line's width covered, in PNG pixels), and writes
results/grounding-<timestamp>/probe.json plus probe.md. The verdict is
PASS when at least 9 of 10 runs pass. Also records the verdict in
fixtures/grounding_verdict.json.

Run: uv run python scripts/probe_grounding.py [--effort low|medium]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import grounding as grounding_mod
from app.spend import cost_usd, usage_of

RESULTS = Path("results")
VERDICT_PATH = grounding_mod.FIXTURES / "grounding_verdict.json"
PASS_MARK = 9


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effort", default="low",
                        help="reasoning effort for the grounding calls")
    parser.add_argument("--runs", type=int, default=10,
                        help="how many locate_line calls to score")
    return parser.parse_args(argv)


def render_markdown(payload: dict) -> str:
    lines = [
        "# Grounding probe",
        "",
        f"Effort: {payload['effort']} · runs: {payload['runs']} · "
        f"passed: {payload['passed']} · verdict: **{payload['verdict']}**",
        f"Cost: ${payload['usd']:.4f} · "
        f"model: {payload['model'] or '?'} · {payload['date']}",
        "",
        f"Line: `{payload['line_text']}`",
        f"Band (PNG pixels): {payload['band']} · "
        f"PNG size: {payload['png_size']}",
        "",
        "| run | bbox (0-1000) | centre y (px) | coverage | pass | seconds |",
        "|---|---|---|---|---|---|",
    ]
    for run in payload["run_results"]:
        box = run["bbox"]
        box_text = ("none" if box is None else
                    f"{box['x_min']},{box['y_min']},"
                    f"{box['x_max']},{box['y_max']}")
        centre = run["score"] or {}
        centre_text = "—"
        coverage_text = "—"
        if box and centre:
            centre_text = f"{centre['centre_y']:.1f}"
            coverage_text = f"{centre['coverage']:.3f}"
        lines.append(
            f"| {run['n']} | {box_text} | "
            f"{centre_text} | {coverage_text} | "
            f"{'PASS' if run['pass'] else 'FAIL'} | {run['seconds']} |")
    lines += ["", f"Verdict: {payload['passed']} of {payload['runs']} "
                  f"on target — {payload['verdict']}",
              f"(pass mark: {PASS_MARK} of {payload['runs']})."]
    if payload.get("failures"):
        lines += ["", "Failures:"] + [
            f"- run {item['n']}: {item['reason']}"
            for item in payload["failures"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    entries = grounding_mod.load_lines()
    arrival = next((entry for entry in entries
                    if "warehouse" in str(entry.get("text") or "")), None)
    if arrival is None:
        print("arrival line not found in lines.json", file=sys.stderr)
        return 2
    line_text = arrival["text"]
    size = grounding_mod.png_size_of()
    if size is None:
        print("scan PNG missing", file=sys.stderr)
        return 2

    run_results: list[dict] = []
    failures: list[dict] = []
    total_usd = 0.0
    model: str | None = None
    for number in range(1, args.runs + 1):
        captured: dict = {}

        def _capture(instructions, input_items, **kwargs):
            from app.adapter import respond as _respond
            result = _respond(instructions, input_items, **kwargs)
            captured.update(result)
            return result

        try:
            bbox = grounding_mod.locate_line(
                grounding_mod.SCAN_PNG_PATH, line_text,
                effort=args.effort, respond_fn=_capture)
            reason = None if bbox is not None else "no_box"
        except Exception as exc:  # noqa: BLE001 - probe records, never dies
            bbox, reason = None, f"{type(exc).__name__}: {exc}"[:300]
        inputs, cached, outputs = usage_of(captured)
        run_usd = cost_usd(inputs, cached, outputs)
        total_usd += run_usd
        model = model or captured.get("model")
        score = grounding_mod.score_box(bbox, arrival, size) \
            if bbox is not None else None
        passed = bool(score and score["pass"])
        if reason is not None:
            failures.append({"n": number, "reason": reason})
        run_results.append({
            "n": number, "bbox": bbox, "score": score, "pass": passed,
            "model": captured.get("model"),
            "response_id": captured.get("response_id"),
            "seconds": round(captured.get("seconds", 0.0), 2),
            "input_tokens": inputs, "cached_tokens": cached,
            "output_tokens": outputs, "usd": round(run_usd, 6),
            "reason": reason,
        })
        print(f"run {number}/{args.runs}: "
              f"{'PASS' if passed else 'FAIL'} "
              f"{bbox} ${run_usd:.4f}", flush=True)

    passed = sum(1 for run in run_results if run["pass"])
    verdict = "PASS" if passed >= PASS_MARK else "FAIL"
    stamp = datetime.now(timezone.utc)
    folder = RESULTS / f"grounding-{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "effort": args.effort, "runs": args.runs, "passed": passed,
        "verdict": verdict, "pass_mark": PASS_MARK,
        "usd": round(total_usd, 4),
        "model": model,
        "date": stamp.date().isoformat(),
        "png": grounding_mod.SCAN_PNG_NAME,
        "png_size": list(size),
        "line_text": line_text,
        "band": arrival,
        "run_results": run_results,
        "failures": failures,
    }
    (folder / "probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (folder / "probe.md").write_text(render_markdown(payload),
                                     encoding="utf-8")
    VERDICT_PATH.write_text(json.dumps({
        "verdict": verdict, "passed": passed, "runs": args.runs,
        "effort": args.effort,
        "probe_folder": f"{folder.as_posix()}",
        "date": stamp.date().isoformat(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{verdict}: {passed} of {args.runs} on target "
          f"(${total_usd:.4f}) -> {folder.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
