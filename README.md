# Night Shift

An overnight manager agent for a small business owner, built on Muse Spark 1.3 through the Meta Model API. You hand over one job at 21:30 and go to bed. The agent works it through the night, acts only under the permissions you gave it, wakes you only when the evidence says it must, and leaves you a morning page: what was done, what needs a decision, the exact messages waiting for your approval, and what could not be verified.

Built solo for the Meta Global AI Developer Hackathon 2026, Indie track, theme "Build for Your World".

- Live: (URL)
- Video: (URL)
- How it was built, and what was written before the building period: `PROVENANCE.md`
- Build log: `BUILDLOG.md`

## Status

Day 1. Everything below this line is filled in as it is built.

## Deploy (Fly.io, app `night-shift-demo`, region Stockholm)

The app reads its run records (and later its SQLite file) from `DATA_DIR`,
default `./data` locally; on Fly `DATA_DIR=/data`, a 1 GB volume. The image
already contains `data/` and `fixtures/` as seed content. The live site key
stays a Fly secret; it is never written into files. From this folder, once the
hosting account exists, run these three commands (do not run them before then):

```powershell
fly launch --copy-config --no-deploy
fly secrets set NIGHT_SHIFT_API_KEY_LIVE=$env:NIGHT_SHIFT_API_KEY_LIVE
fly deploy
```

## Disclosure

Personal project, built on my own time with no company code, data or resources. All code, tests and fixtures were written by Muse Code. A general AI assistant helped with planning, the written brief, the prompts given to Muse Code, this README and the video script. Details in `PROVENANCE.md`.
