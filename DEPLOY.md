# Deploy and run

## Live site (Fly.io)

App `night-shift-demo`, region `arn` (Stockholm), shared-cpu-1x, 1 GB
volume `night_shift_data` mounted at `/data`. The Docker image bakes in
`data/` and `fixtures/` as seed content; files already on the volume win.
Live at https://night-shift-demo.fly.dev/.

From the repo root:

```powershell
fly launch --copy-config --no-deploy
fly secrets set NIGHT_SHIFT_API_KEY_LIVE=$env:NIGHT_SHIFT_API_KEY_LIVE
fly deploy
```

## Environment variables

Names only. Values live in the environment (or Fly secrets), never in files.

- `NIGHT_SHIFT_API_KEY_LIVE` — Meta Model API key for the live site, read
  first. Set as a Fly secret; it is never written into files.
- `NIGHT_SHIFT_API_KEY_EVAL` — fallback key for local runs and the
  evaluation.
- `RUN_TOKEN` — `POST /jobs/run` needs header `X-Run-Token` equal to this,
  else 403. Set as a Fly secret.
- `DAILY_CAP_USD` — daily spend cap for live visitor resumes, in USD
  (default 5).
- `RECORDED_JOB` — pins the export replayed on the front door (a job id, a
  file name, or a path). Empty means the latest hero run with a wake and a
  hold.
- `DATA_DIR` — run data directory (`./data` locally; `/data` on Fly).
- `VAPID_PUBLIC_KEY` — base64url VAPID public key for Web Push to the
  owner's phone. Generated once by `scripts/make_vapid.py`; set as a Fly
  secret on the live site.
- `VAPID_PRIVATE_KEY` — base64url VAPID private key. Never printed except
  once by `scripts/make_vapid.py`; set as a Fly secret, never in files.
- `VAPID_SUBJECT` — a `mailto:` or `https:` URL identifying the push
  sender (default `mailto:owner@example.invalid`).
- `PUSH_ENABLED` — set to `1` to let the notify step deliver real pushes
  for the operator's own job (default off; when off, or when the keys are
  missing, the notify step logs `push_skipped` with reason `disabled`).

## Run it locally

Prerequisites: Python and `uv`. Dependencies install with `uv sync`; the
virtual environment lives in `.venv` inside the repo.

```powershell
uv run uvicorn app.main:app --port 8123
```

Open http://127.0.0.1:8123/ (host port 8080 is taken by another local
service, so local checks use 8123). The front door replays the recorded
run from the bundled exports, so it renders with no API key set. Answering
as the owner resumes live with real Muse Spark calls and needs
`NIGHT_SHIFT_API_KEY_LIVE` (or `NIGHT_SHIFT_API_KEY_EVAL`) in the
environment.

## Owner phone push (M14)

The night's notify step can deliver a real Web Push notification to the
owner's own phone, for the operator's own job only (visitor jobs stay
simulated). Needs `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and
`PUSH_ENABLED=1` in the environment (Fly secrets on the live site);
`VAPID_SUBJECT` is optional.

Subscribe the phone on the deployed site (token from `RUN_TOKEN`):

```text
https://night-shift-demo.fly.dev/owner/phone?token=...
```

Tap "Subscribe this phone", accept the notification permission, then tap
"Send test push" to verify. The service worker lives at
`/static/sw.js` and only shows the notification and opens its URL.
