# Night Shift

An overnight manager agent for a small business owner, built on Muse Spark 1.3 through the Meta Model API. You hand over one job at 21:30 and go to bed. The agent works it through the night, acts only under the permissions you gave it, wakes you only when the evidence says it must, and leaves you a morning page: what was done, what needs a decision, the exact messages waiting for your approval, and what could not be verified.

Built solo for the Meta Global AI Developer Hackathon 2026, Indie track, theme "Build for Your World".

- Live: https://night-shift-demo.fly.dev/ (Day 1: hello page and /evidence)
- Video: (URL)
- How it was built, and what was written before the building period: `PROVENANCE.md`
- Build log: `BUILDLOG.md`

## Status

Day 3 (Oct 27). One job runs the full night for real: sources read, the 00:38 revised quote, six checks, a wake question, an owner answer, one H-2041 hold and a morning page.
The front door at `/` replays the recorded hero run and lets a visitor answer into a new live job, guarded by a daily spend cap and a 2-resume limit.
Fixtures carry the studio's ordering contact and print file, which the gateway checks in code; version-bound approvals, operation ids and the contact-list leak flag are enforced with contract tests.
Recorded hero (Oct 27): notified 00:47 about venue receipt only, hold placed on resume. Recorded contrast: decided to act itself but left the hold unplaced.
Live: https://night-shift-demo.fly.dev/ (redeploy pending). Next: reliability at the public URL, then runtime limits and evaluation.

## Deploy (Fly.io, app `night-shift-demo`, region Stockholm)

The app reads its run records (and later its SQLite file) from `DATA_DIR`,
default `./data` locally; on Fly `DATA_DIR=/data`, a 1 GB volume. The image
already contains `data/` and `fixtures/` as seed content. The live site key
stays a Fly secret and is read first (falling back to NIGHT_SHIFT_API_KEY_EVAL); it is never written into files. From this folder, once the
hosting account exists, run these three commands (do not run them before then):

```powershell
fly launch --copy-config --no-deploy
fly secrets set NIGHT_SHIFT_API_KEY_LIVE=$env:NIGHT_SHIFT_API_KEY_LIVE
fly deploy
```

## Results

Recorded runs (muse-spark-1.3, Tue Oct 27; exports in `data/runs/`, details in `BUILDLOG.md`):
- Hero `6c7c7c742513`: notified at 00:47 ("Can Sjosalen, Sjogaten 5, 5003 Bergen receive the 100 tote bags in the Wed Nov 11 08:00-12:00 van window?"), answered 01:05, hold H-2041 placed on resume first try, morning page with 3 drafts.
- Contrast `37f34f71d9df`: venue receipt verified from its own file, decided `act_under_permission` at 22:30 and placed hold H-2041 by itself under the standing permission (gateway 8/8, first try), no notification. A second identical contrast run (`36e41552448b`) disagreed with it: it woke at 00:47 asking about venue receipt though its own venue claim quoted the Wednesday delivery line, and placed no hold. Same settings, opposite nights — recorded honestly in `BUILDLOG.md`.

## Disclosure

Personal project, built on my own time with no company code, data or resources. All code, tests and fixtures were written by Muse Code. A general AI assistant helped with planning, the written brief, the prompts given to Muse Code, this README and the video script. Details in `PROVENANCE.md`.
