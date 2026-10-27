"""Run hero + contrast nights for real, once each. Prints per-call stats."""
import json
import sys
sys.path.insert(0, ".")
import time
from datetime import datetime, timezone

import app.runner as runner
from app.adapter import respond as real_respond

CALLS: list[dict] = []
CURRENT = {"variant": "?"}


def wrapped(instructions, input_items, **kwargs):
    t0 = time.time()
    result = real_respond(instructions, input_items, **kwargs)
    dt = time.time() - t0
    usage = result.get("usage") or {}
    CALLS.append({"variant": CURRENT["variant"], "phase": CURRENT.get("phase", "?"),
                  "seconds": round(dt, 1),
                  "in": usage.get("input_tokens"), "out": usage.get("output_tokens"),
                  "reasoning": (usage.get("reasoning_tokens") or (usage.get("output_tokens_details") or {}).get("reasoning_tokens")),
                  "model": result.get("model"), "status": result.get("status")})
    print(f"[{CURRENT['variant']}/{CURRENT.get('phase')}] {dt:.1f}s in={usage.get('input_tokens')} out={usage.get('output_tokens')} status={result.get('status')}", flush=True)
    return result


runner.respond = wrapped

for variant in ("hero", "contrast"):
    CURRENT.update({"variant": variant, "phase": "night"})
    summary = runner.run_job(variant=variant)
    job_id = summary["job_id"]
    print(f"VARIANT={variant} JOB={job_id} STATUS={summary['status']}")
    if variant == "hero" and summary["status"] == "waiting_for_owner":
        runner.store_answer(job_id, "Bergen: the venue can receive it")
        CURRENT["phase"] = "resume"
        res = runner.resume_job(job_id, respond_fn=wrapped)
        print(f"HERO RESUME STATUS={res['status']}")
    out = runner.export_job(job_id)
    print(f"EXPORT={out}")

print(json.dumps(CALLS, indent=1))
