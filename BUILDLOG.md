# Build log

A few lines per session: what was built, what failed, what was cut. Oslo time.

## Tue Oct 27

- 10:12 Repo created and pushed (public, hrminator/night-shift). Muse Code 1.4.13 installed; Contributor mode off via MUSE_CONTRIBUTOR_MODE=0; foreign skill root disabled. Model: muse-spark-1.3.
- Gate for today: a deployed real model result with its source evidence.
- 11:35 Sandbox set up. Two pay-as-you-go API keys created (live, eval) and kept in the user environment. Spend alert set. $150 hackathon credits claimed via the organisers' form.
- Day 1 step 1 (Muse Code session): skeleton committed (`pyproject.toml`, `.venv` in repo, FastAPI + uvicorn + httpx + pytest, hello page at `/` served by `uv run uvicorn app.main:app`). `pytest`: 4 passed (hello view + adapter request-shape tests).
- Day 1 step 2 (Muse Code session): `app/adapter.py` committed. Thin Responses client for `https://api.meta.ai/v1`, model `muse-spark-1.3`, key from `NIGHT_SHIFT_API_KEY_EVAL`. Sends `store:false`, `include:["reasoning.encrypted_content"]`, resends instructions/tools/effort every call, never `previous_response_id`, always `max_output_tokens`. Logs request/response bodies (no Authorization header) to `logs/responses-<date>.jsonl`. Keeps output items in order for replay; on HTTP 400 retries once with reasoning items dropped whole and logs it.
- NOT run yet: `uv run python scripts/probe_spark.py` (efforts minimal/low/medium) and `logs/reasoning-2026-10-27.json`. The sandboxed shell cannot see `NIGHT_SHIFT_API_KEY_EVAL`, cannot bind loopback sockets (so the hello page was verified by route inspection + direct view call, not a live HTTP request), and cannot fix git ownership globally. Owner: from a normal shell run `Set-Location C:\Users\herma\night-shift; uv run python scripts/probe_spark.py`, paste its three JSON lines below, then save the reasoning items. API reachability from here confirmed (unauthenticated GET to `/v1/models` returns 401 `invalid_api_key`).
- 11:40 Verified from a normal shell: hello page answers HTTP 200 at 127.0.0.1:8123 ("Night Shift" + UTC time). Probe against muse-spark-1.3, all three efforts returned identical numbers (41 in / 64 out / 62 reasoning, 2.1-3.3 s) and empty text: the probe's max_output_tokens is too low, so the reply was cut off inside reasoning. Numbers are not a valid effort comparison yet; rerun after the fix. logs/reasoning-2026-10-27.json saved (1 item).
