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
