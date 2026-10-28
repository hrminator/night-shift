# Provenance

Everything in this repository was created during the hackathon building period (Oct 27 - Nov 4, 2026, ET), except where listed below.

## Before the building period (disclosed, not reused)

- Plain-language design documents written Oct 18-26, 2026: the scenario, acceptance scenarios and a build plan. The brief in `AGENTS.md` and the scenario in `SCENARIO.md` are condensed from them. No code.
- One throwaway API smoke-test script (about 70 lines, Oct 18, 2026) that checked a Meta Model API key worked. Not committed, not reused, not shown.

## Who and what built this

- **Built by:** one person with AI tools, Oct 27–Nov 3, 2026. All code, tests and fixtures were written by Muse Code (muse-spark-1.3), driven by the prompt files in `prompts/`.
- **Planning and direction help:** a general AI assistant (Claude) wrote and sent those prompt files and the README prose, and ran Muse Code headless; API details in the prompts are copied from Meta's docs and labelled as such. I set direction, made every decision and reviewed the results. Plain-language design documents written before Oct 27 were used as inputs; no pre-event code is in this repository.
- **Models in the product:** Muse Spark 1.3 through the Meta Model API (Responses API).

## Dependencies

(List every package with its version and license as it is added.)

Added Tue Oct 27 (Python 3.13.5, `uv sync`): fastapi 0.162.0 (MIT), uvicorn 0.54.0 (BSD-3-Clause), httpx 0.28.1 (BSD-3-Clause), pytest 9.1.1 (MIT), plus their transitive deps pinned in `uv.lock`.

Added Tue Oct 27 (`uv add`): reportlab 5.1.0 (BSD), Pillow 13.0.0 (HPND) — for generating the Baltic quote PDFs and the scan-styled raster effect.

Added Tue Oct 27: tzdata 2026.5 (Apache-2.0) — provider of IANA time zone data, needed for the virtual clock on Windows.

Added Wed Oct 28 (`uv add`): pywebpush 2.5.0 (MPL-2.0) with py-vapid 1.9.6 (MPL-2.0), http-ece 1.2.1 (MIT), cryptography 50.0.2, requests 2.34.2 and aiohttp 3.14.5 (plus transitive deps pinned in `uv.lock`) — Web Push encryption and delivery from the notify step to the owner's phone (M14).

Added Wed Oct 28 (`uv add --dev`): playwright 1.64.1 (Apache-2.0) with greenlet 3.5.6 and pyee 14.0.0 — headless-Chromium screenshots of the S0 comps (`tmp_shoot.py`, run once, not committed). Dev only, not shipped in the image; the browser (Chromium headless shell, outside the repo) came from `playwright install chromium`.

## Fonts and assets

(List every font, icon and image with its source and license as it is added. None yet.)

Added Wed Oct 28 (S0 design comps, loaded from the Google Fonts CDN with `display=swap`, not vendored): Newsreader (OFL) for the question note, quote sheet, greeting and draft letters; Geist (OFL) for the UI; Geist Mono (OFL) for the clock, times, ids, hashes, tags and receipt. Grain is an inline SVG feTurbulence data URI written for this project.

## Fixtures

All fixtures are fictional and were written for this project. The businesses, suppliers, venue, quotes, portal records and people do not exist. Any resemblance is unintended; names were checked against public registers before use.

(List each fixture file and the date it was written as it is added.)

Written Tue Oct 27 (all fictional, generated in this repo; PDFs built by `scripts/make_fixtures.py` with reportlab + Pillow):

- `fixtures/brief.md` — the evening brief and standing permission, verbatim from SCENARIO.md.
- `fixtures/nordtrykk.html` — P1's shop page: banner, lead time, price, plus a hidden AI instruction (HTML comment + white-on-white text) to a fictional outside address.
- `fixtures/vestland_portal.json` — P2's portal record, version 1: Nov 6 run, hold rules, Oslo-freight-full, Bergen van window, prices, hold form fields.
- `fixtures/baltic_quote_original.pdf` — P3's original quote Q-1187 (clean text PDF).
- `fixtures/baltic_quote_Q-1187-B.pdf` — revised quote, scan-styled: raster image only (rotated, noise), no text layer.
- `fixtures/baltic_quote_Q-1187-B_text.pdf` — same revised content as a normal text PDF, for comparison.
- `fixtures/baltic_quote_Q-1187-B.png` — written Wed Oct 28 (Muse Code session): the exact raster placed in the scan-styled PDF (post-rotation, post-noise), kept for the pages.
- `fixtures/baltic_quote_Q-1187-B@2x.png` — written Wed Oct 28 (Muse Code session, B1b): the same page at exactly twice the size (1190x1682), same rotation and noise, as sent to the grounding call; its bands are the 1x bands times 2.
- `fixtures/baltic_quote_Q-1187-B.lines.json` — written Wed Oct 28 (Muse Code session): scale 1 metadata plus one entry per rendered line with its text and 1x pixel band, computed from the draw positions and font metrics plus the 0.8° rotation's vertical displacement; B1b records scale at the top and the @2x bands are the 1x bands times 2.
- `fixtures/grounding_verdict.json` — written Wed Oct 28 (Muse Code session): the latest grounding probe's verdict {verdict, passed, runs, effort, probe_folder, date}; currently FAIL 7/10 at medium effort.
- `fixtures/baltic_shipping_terms.html` — P3's terms page (transit not guaranteed).
- `fixtures/venue_confirmation.md` — Sjøsalen booking for Thu Nov 12, event hours only.
- `fixtures/addresses.json` — Oslo office (default) and Sjøsalen venue addresses.
- `fixtures/decision_facts.json` — the ONE decision-facts file: venue delivery window (null) and recipient-can-receive (null), with the contrast-run values documented inside.
- `fixtures/events.json` — scheduled events: 21:30 handoff, 00:38 revised quote arrives.
- `fixtures/studio.json` — written Day 3 step C (Muse Code session): the studio's ordering contact (Kari Strandli, fictional name/role/email/phone), the print file name (fjord-fern-logo-print.pdf, 300 dpi, black, name only) and the studio's contact list (owner, ordering contact, venue contact). Read as a source in every night turn; the gateway checks the hold's contact and print file against it and uses its list for the draft leak check. The brief's "Addresses and contacts you may use" line names both fields.

## Evaluation (Day 4 step A, Muse Code session)

All evaluation material is new work written for this project; no external benchmarks, datasets or harnesses are reused.

- `cases/*.json` (12 files) — the wake pairs (timing/evidence/alternatives/necessity must- and no-wake) and the complete-job cases W1-W4. Each states its overrides plus expected words (quoting SCENARIO.md; AGENTS.md defines no verbatim outcome lines to quote) and machine-checkable predicates.
- `app/eval_world.py` — case loader applying overrides in memory only; fixture files on disk are never touched.
- `app/eval_night.py` + `scripts/eval.py` — harness running each case as a fresh night in a throwaway DATA_DIR with real muse-spark-1.3 calls, exporting every job.
- `app/eval_score.py` — scorer reading only the app's event log; cost from the harness's own usage records at Spark 1.3 prices ($1.25 input, $0.15 cached input, $4.25 output per million).
- `results/` — pilot outputs committed per part 4; every run marked development run.
