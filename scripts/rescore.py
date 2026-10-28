"""Re-score existing results/ folders with the current scorer.

No model calls: each record's exported job is re-read from disk and scored
again with ``eval_score.evaluate`` against its case file, then the folder
summary, results.json and report.md are rewritten in place. Prints the old
and new summary per folder so the caller can record the delta.

Usage:
  uv run python scripts/rescore.py [folder ...]
  (default: every results/*/results.json with eval records)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app import eval_score, eval_world  # noqa: E402
from scripts.eval import render_report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = ("done", "waiting_for_owner", "decision_done")


def rescore_folder(folder: Path) -> dict:
    """Re-score one folder; return {"old": ..., "new": ..., "flips": ...}."""
    path = folder / "results.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    old_summary = dict(payload.get("summary") or {})
    flips: list[str] = []
    for record in payload.get("records") or []:
        export = record.get("export", "")
        target = ROOT / export if export else None
        if target is None or not target.exists():
            continue
        events = json.loads(target.read_text(encoding="utf-8"))["events"]
        case = eval_world.load_case(record["case"])
        scored = eval_score.evaluate(events, case)
        before = record.get("pass")
        record["observed"] = scored["observed"]
        record["predicates"] = scored["predicates"]
        record["pass"] = scored["pass"]
        if record.get("status") not in TERMINAL:
            record["pass"] = False
            record["note"] = record.get("note", record.get("status", ""))
        if before != record["pass"]:
            flips.append(f"{record['case']}/{record['run']}:"
                         f" {before}->{record['pass']}")
    payload["summary"] = eval_score.summarize(payload.get("records") or [])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    (folder / "report.md").write_text(render_report(payload),
                                      encoding="utf-8")
    return {"old": old_summary, "new": payload["summary"], "flips": flips}


def main(argv: list[str]) -> int:
    folders = ([Path(name) for name in argv[1:]] if len(argv) > 1
               else sorted(ROOT / "results" for _ in [0]))
    if len(argv) <= 1:
        folders = sorted(path for path in (ROOT / "results").glob("*")
                         if (path / "results.json").is_file())
    for folder in folders:
        try:
            result = rescore_folder(folder)
        except (KeyError, ValueError, OSError) as exc:
            print(f"SKIP {folder.name}: {exc}")
            continue
        old, new = result["old"], result["new"]
        print(f"{folder.name}: must {old.get('must_wake_surfaced')}/"
              f"{old.get('must_wake_runs')} -> {new.get('must_wake_surfaced')}/"
              f"{new.get('must_wake_runs')} in window"
              f" (late/wrong {new.get('must_wake_late_or_wrong')});"
              f" needless {old.get('needless_wakes')}->"
              f"{new.get('needless_wakes')};"
              f" complete {old.get('complete_finished')}/"
              f"{old.get('complete_runs')}->{new.get('complete_finished')}/"
              f"{new.get('complete_runs')};"
              f" premature {new.get('premature_holds')};"
              f" claims-missing {old.get('claims_missing_source')}->"
              f"{new.get('claims_missing_source')};"
              f" flips: {result['flips'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
