# Provenance

Everything in this repository was created during the hackathon building period (Oct 27 - Nov 4, 2026, ET), except where listed below.

## Before the building period (disclosed, not reused)

- Plain-language design documents written Oct 18-26, 2026: the scenario, acceptance scenarios and a build plan. The brief in `AGENTS.md` and the scenario in `SCENARIO.md` are condensed from them. No code.
- One throwaway API smoke-test script (about 70 lines, Oct 18, 2026) that checked a Meta Model API key worked. Not committed, not reused, not shown.

## Who and what built this

- **Builder:** Muse Code (Meta), directed by the owner. All code, fixtures, prompts, tests and the case files were written in Muse Code sessions during the building period.
- **Planning and direction help:** a general AI assistant (Claude) helped write the plan, this brief, the scenario text, the README and the video script, and drafted the prompts given to Muse Code on the owner's direction. It wrote no code, fixtures or tests; those are Muse Code's work.
- **Models in the product:** Muse Spark 1.3 through the Meta Model API (Responses API).

## Dependencies

(List every package with its version and license as it is added.)

Added Tue Oct 27 (Python 3.13.5, `uv sync`): fastapi 0.162.0 (MIT), uvicorn 0.54.0 (BSD-3-Clause), httpx 0.28.1 (BSD-3-Clause), pytest 9.1.1 (MIT), plus their transitive deps pinned in `uv.lock`.

Added Tue Oct 27 (`uv add`): reportlab 5.1.0 (BSD), Pillow 13.0.0 (HPND) — for generating the Baltic quote PDFs and the scan-styled raster effect.

## Fonts and assets

(List every font, icon and image with its source and license as it is added. None yet.)

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
- `fixtures/baltic_shipping_terms.html` — P3's terms page (transit not guaranteed).
- `fixtures/venue_confirmation.md` — Sjøsalen booking for Thu Nov 12, event hours only.
- `fixtures/addresses.json` — Oslo office (default) and Sjøsalen venue addresses.
- `fixtures/decision_facts.json` — the ONE decision-facts file: venue delivery window (null) and recipient-can-receive (null), with the contrast-run values documented inside.
- `fixtures/events.json` — scheduled events: 21:30 handoff, 00:38 revised quote arrives.
- `fixtures/studio.json` — written Day 3 step C (Muse Code session): the studio's ordering contact (Kari Strandli, fictional name/role/email/phone), the print file name (fjord-fern-logo-print.pdf, 300 dpi, black, name only) and the studio's contact list (owner, ordering contact, venue contact). Read as a source in every night turn; the gateway checks the hold's contact and print file against it and uses its list for the draft leak check. The brief's "Addresses and contacts you may use" line names both fields.
