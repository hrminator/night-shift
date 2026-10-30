# Night Shift

*An overnight manager on Muse Spark that works your job while you sleep, acts only inside the permission you gave it, and is built to wake you only when the evidence says it must; the results below show how often it gets that right.*

(12-second film of one night: coming Thu Oct 29)

[Try it live](https://night-shift-demo.fly.dev/) · 3-min video (coming Nov 2) · [Results](#results) · [How it was built](#built-during-the-hackathon)

- It changes its mind when the evidence changes.
- It can act, narrowly.
- Measured, not claimed.

*Fictional studio and suppliers · real Muse Spark calls, recorded and replayed at compressed speed; the answer step runs live · supplier systems and mail simulated · built Oct 27–Nov 3, all code written by Muse Code.*

## Try it in two minutes

The front door replays the recorded hero night up to the 00:47 question, then stops and hands you the owner's buttons. Your tap copies the saved job into a new live job with its own ids and outbox and resumes with real Muse Spark calls: the hold comes back from the simulated portal and the three drafts update. You approve one draft into the on-page outbox, and if you edit a word first the approval flips back to awaiting.

"Change one fact instead", under the question's buttons, runs Night B live: the same night with one fixture line changed (the venue accepts Wednesday deliveries), fresh from 21:30 on a new copy, streaming each step as it is logged. When the spend cap is reached it shows the recorded Night B instead, labelled.

## One night, minute by minute

Recorded hero run `6c7c7c742513` (muse-spark-1.3, Tue Oct 27), following `SCENARIO.md`. The night is built to wake you only when it must:

| Time | What happens |
|---|---|
| 21:30 | Handoff: one job, 100 tote bags for the Thu Nov 12 customer day. The owner goes to bed. |
| 21:35–22:30 | Spark reads the sources. Rannavere Q-1187 commits delivery by Nov 9, so it is the plan of record and no hold is placed. |
| 00:38 | The one scheduled event: revised quote Q-1187-B arrives and replaces Q-1187. Same price, now dispatch-only. |
| 00:39–00:46 | The six named checks, each logged: no source commits to Rannavere arrival, the original quote is replaced, Nordtrykk is too late, Vestland–Oslo is full, venue receipt is unverified, and nobody would reply before 02:00. |
| 00:47 | Decision: wake. The owner is notified with one question — can Sjøsalen receive the van Wed 08:00–12:00 — answer due 01:50. |
| 01:05 | The owner answers: "Bergen: the venue can receive it". |
| 01:05 | The gateway passes 8/8 and one hold goes to the simulated portal. Acknowledgement H-2041 returns. |
| 01:06–01:15 | The saved job resumes: cost recalculated, three drafts redone. |
| 07:00 | Morning page: comparison, hold H-2041, three approvals. The hold ends at 09:00 unless the order is confirmed. |

## How it works

- An append-only event log in SQLite (WAL): the owner's answer, the permission used, the gateway result and the effect are four separate records, and events are never edited.
- A virtual clock (21:30–09:30) with deadline arithmetic in code: portal cutoff 02:00, answer due 01:50, latest safe notification 01:30. The agent notifies as soon as the decision becomes necessary.
- Four supervision rules enforced in code: a wake decision must exist before any question; all six checks must be logged after the 00:38 event; one open question per job, so a repeat ask is refused; and no question is ever asked after the answer deadline.
- Every hold passes the gateway's eight checks — permission, target, fields, terms, time, sources, privacy, once-only — each one logged. Anything outside the permission becomes a draft approval item, never an effect.
- Approvals bind to one exact text (content + recipient), valid 30 minutes or until the item's deadline, whichever is first. Editing a draft voids its approval, and the Vestland order approved after 09:00 is refused because the hold has lapsed.
- A simulated portal returns hold H-2041 and a simulated outbox delivers approved drafts. Every effect carries a unique operation id inserted in the same transaction, so retries and double clicks return the same record.

## How it uses Meta's models

Every Meta API call goes through [app/adapter.py](app/adapter.py), called from [scripts/probe_spark.py](scripts/probe_spark.py), [scripts/read_sources.py](scripts/read_sources.py), [scripts/replay_check.py](scripts/replay_check.py), [scripts/run_night.py](scripts/run_night.py) and [scripts/eval.py](scripts/eval.py).

- The Responses API with model `muse-spark-1.3`: every call sends `store:false` with `include:["reasoning.encrypted_content"]`, resends instructions, tools and effort each time, and never uses `previous_response_id`. Encrypted reasoning replay works: in a matched replay of the same paused night with the same answer (recorded night 6c7c7c742513, 3 runs per arm, results/replay-matched-20261028T202510Z/), resume with replayed reasoning used a mean of 53,253 input tokens vs 132,037 with the source documents re-sent[^replay]; a Day-1 replay check returned 1107 in / 434 out with the items intact. If a replay gets HTTP 400, the adapter drops the reasoning items whole, retries once, and logs that it did.
- The image-only page read: Spark read the scan-styled revised quote correctly ("Delivery: Goods will leave our warehouse by 10 November."). That page was rendered by [scripts/make_fixtures.py](scripts/make_fixtures.py) as a rotated, noisy raster with no text layer — not a scan of a real document.
- Effort per call type: night turns run at medium with `max_output_tokens` 8192; source extraction runs at low with 2048. The per-call probe measured minimal (41 in / 241 out / 229 reasoning, 2.11 s), low (41 / 350 / 339, 1.85 s) and medium (41 / 1024 / 1022, 4.4 s, truncated with empty text — medium needs at least 2048).
- Tool calling uses `tool_choice:"auto"` with parallel tool calls; a call whose arguments fail the schema is refused and logged as malformed, and a turn that answers in plain text is nudged once, then marked failed and recorded.
- The builder is Muse Code: all code commits are Muse Code's, driven by the prompt files in [prompts/](prompts/). The exact instruction text the app sends is published in [docs/instructions.md](docs/instructions.md), generated from the code.
- The grounding call: after the reassess turn, the app sends the scan-styled revised quote as a PNG (the @2x render, 1190x1682) plus the exact line Spark quoted and asks for its bounding box on a 0-1000 grid (call type `ground`, `text.format` json_schema, outside the decision context). This call does not detect the change — Spark found the change reading the page itself; it only points at the line Spark quoted. The probes scored 10 runs each against the fixture's line band (vertical centre in band plus 70% width coverage): 2 of 10 on target at low effort (1x), 7 of 10 at medium (1x), 0 of 10 at medium (2x), 0 of 10 at medium with a tighter instruction (2x); verdict FAIL, so a failed probe leaves the quoted line underlined with no box. 10 runs per probe is a small sample. The live call is off (GROUNDING_ENABLED defaults to off) because the verdict is FAIL; the probe scripts and fixtures stay, and the probes remain in results/.

[^replay]: Unmatched observation from Day 1, kept for context only: the first source-reading call used 6349 input tokens and its replay turn used 2106.

## Results

Pilot table, muse-spark-1.3, medium, 12 constructed situations, 2 arms, 1 repetition each arm (re-scored Oct 28 with the in-window, right-question, and premature-hold rules). Decision-only and complete-job results are never merged. All runs below are development runs; full per-episode reports are in `results/`.

| arm | must-wake in window | needless wakes | late/wrong wakes | duplicates through / prevented | complete jobs | premature holds | refused / effects | cost |
|---|---|---|---|---|---|---|---|---|
| supervision (`results/20261027T125850Z`) | 4/4 | 2/4 | 0 | 2 runs / 0 | 4/4 | 1 | 3 / 3 | $2.28 |
| direct (`results/20261027T134105Z` + `results/20261027T135332Z`) | 4/4 | 1/4 | 0 | 2 runs / 0 | 4/4 | 1 | 3 / 3 | $2.12 |

The supervision pilot's misses: needless wakes on alternatives_no_wake (the 4-working-day Nordtrykk page did not stop the wake) and timing_no_wake (woke at 02:30, after the cutoff), plus duplicate notifications on W1_timely_answer and necessity_must_wake, which asked in the read turn and again after the event. After the Oct 27 ask rules, reruns pass timing_no_wake (the 02:30 ask refused in code), W1 (one hold, one prevented duplicate) and necessity_must_wake, while alternatives_no_wake still wakes needlessly. The direct pilot's misses: a needless wake on alternatives_no_wake, and two first-pass episodes (W1, W2) lost to a transport error (WinError 10054) and rerun once into a second folder — the table counts the reruns. Re-scoring Oct 28 with the new rules added one premature hold per arm (necessity_no_wake held at 22:30, before the revised quote) and one claim without a resolvable source on the supervision arm. Honestly scored, supervision does not yet beat direct on needless wakes (2 vs 1); the demonstrated gains are the duplicate-question rule and the never-ask-after-deadline rule, both proven on reruns.

Cost vocabulary: every figure names its job or folder. The one recorded night 6c7c7c742513 cost $0.26 with 50% of input tokens served from cache (17 calls, measured from logs/responses-2026-10-27.jsonl; the same line is on the front door and the comps). $0.19 is the mean over 12 development runs (results/20261027T125850Z, $2.2812 total). 70–76% are the per-night cache shares of the two W1 nights in results/20261028T082246Z (70.0% and 76.4%; 74.0% pooled over the folder).

Final runs: 12 constructed situations × 2 arms × 3 repetitions on the frozen tag, planned for Sat Oct 31.

Contrast runs so far: neither fresh contrast run counts as a correct quiet night. Run 37f34f71d9df placed its hold at 22:30 while the original quote still committed arrival, so under the scenario's own rule it is a premature hold, not a correct quiet night; run 36e41552448b woke at 00:47 asking about venue receipt though its own venue claim quoted the Wednesday delivery line.

Night B ("change one fact", supervision necessity_no_wake x3): the first runs (`results/20261028T205824Z/`) held without waking in 1 of 3 — run `cde5841a68d2` read the evidence rule correctly at 22:30, then held H-2041 itself at 00:38 without waking (gateway 8/8); runs `db62d30a4a7f` and `5be2c911b63b` held at 22:30 with no notification, premature holds that misread Q-1187's date as dispatch. After the precedence fix the reruns (`results/20261028T221930Z/`) held without waking in 3 of 3, every 22:30 reason citing the Q-1187 line and the precedence rule; run `849015e83ed8` (zero refusals of any kind) is pinned as RECORDED_JOB_B. No run woke the owner in either folder.

**Two behaviours we fixed from measurements.** The premature hold: `results/20261028T205824Z/` showed 2 of 3 Night B runs placing the hold at 22:30 by reading Q-1187's delivery date as dispatch under the terms; `results/20261028T221930Z/` shows 3 of 3 waiting for the 00:38 event after the precedence rules. The misattributed thanks: the hero night and `results/20261028T082246Z/` showed venue notes thanking the venue "for confirming" what only the owner's answer confirmed; the W1 rerun in `results/20261028T222426Z/` states the delivery without crediting the venue (misattributed confirmations 0 — the `attribution_refused` tripwire is proven by contract tests, and did not need to fire). One correction along the way: the replay report's "thanks-venue" count used a loose rule that also catches "Thank you for quote Q-1187-B" and "Please confirm..."; the precise rule finds the venue misattributed in 1 of 3 replay runs and 0 of 3 resend runs.

## What real owners said

Not yet: one procurement professional (a real buyer of printed merchandise) will read a recorded night Thu-Sat and be quoted by role, with permission. One person, not a panel; the true count will be reported.

## Known failures and variance

- The two fresh contrast runs disagree with each other, and neither is a correct quiet night: `37f34f71d9df` placed hold H-2041 by itself at 22:30 with no notification while the original quote still committed arrival, so it is a premature hold under the scenario's own rule; `36e41552448b` woke at 00:47 asking about venue receipt though its own venue claim quoted the Wednesday delivery line. Same settings, same fixtures, opposite nights.
- The pilots' needless wakes: alternatives_no_wake woke in both arms despite the 4-working-day Nordtrykk page, and timing_no_wake woke at 02:30, after the cutoff, in the supervision pilot. Duplicate notifications went through on W1_timely_answer and necessity_must_wake, which asked in the read turn and again after the event.
- Post-pilot fixes, both Oct 27 and enforced in code: the duplicate-question rule (a repeat ask is refused with the open question quoted) and the never-ask-after-deadline rule (an ask past the answer deadline is refused; the outcome is wait_for_morning). The direct arm skips both.
- A removed early instruction tune: "the guaranteed van IS the verified route" (Day 2 tune 2) was removed Oct 27 with the neutral rewrite; the neutral wording woke on its first run with no tune needed.
- A model-judgment miss, untuned: alternatives_no_wake still wakes needlessly after the new rules. Per the brief there is no instruction tuning, so it stands as a miss.
- The 1x medium grounding probe's 3 misses landed on the line directly above or below the quoted line (off-by-one-line at 595x841, where one text line is about 10 px tall).

## What's real, computed and simulated

- MUSE SPARK — reading each source and quoting its delivery line; the wake / act / wait decision with its reason and evidence; the exact question and draft wording.
- CODE — the virtual clock and deadline arithmetic; the gateway checks and refusals; approval binding, expiry and delivery; operation ids and dedup; the spend cap and resume guards; the duplicate-question and ask-deadline rules.
- SIMULATED — the supplier portal and its H-2041 acknowledgement; mail delivery in the outbox; the 00:38 revised-quote arrival as an injected test event; the image-only quote PDF rendered by our fixture script.

## Limitations

- One constructed supplier world: three suppliers, one venue, one night.
- A compressed clock: virtual 21:30–09:30 stands in for a real night.
- An image-only PDF made by our script, not a real scan.
- The gateway cannot judge "only way": whether the hold is really the last route open is the model's judgment, written in its decision record.

## Built during the hackathon

Night Shift was built Oct 27–Nov 3, 2026: see [PROVENANCE.md](PROVENANCE.md), [BUILDLOG.md](BUILDLOG.md) and the [git history](https://github.com/hrminator/night-shift).

Night Shift was built during the hackathon, Oct 27–Nov 3, 2026, by one person with AI tools. All code, tests and fixtures were written by Muse Code (muse-spark-1.3), driven by the prompt files in prompts/. A general AI assistant (Claude) wrote and sent those prompt files and the README prose, and ran Muse Code headless; API details in the prompts are copied from Meta's docs and labelled as such. I set direction, made every decision and reviewed the results. Plain-language design documents written before Oct 27 were used as inputs; no pre-event code is in this repository. The studio, suppliers, venue, documents and contacts are fictional, with invented names. The fictional supplier names were checked against the Norwegian and Estonian company registers on Oct 28: none of the Norwegian names is registered, and the cheap supplier carries the coined name "Rannavere Print OÜ" (its pre-rename working name collided with a similarly named real printer in Tallinn and was replaced before the final recording). The revised quote is an image-only PDF rendered by our fixture script, not a scan of a real document, and it arrives as an injected test event. The supplier portal and mail are simulated. The model calls on the front door are real Muse Spark calls, recorded on [date of the recorded run] and replayed at compressed speed; the answer step runs live. [Opening-shot sentence to be added after the video is recorded.]

## Run it locally and deploy

See [DEPLOY.md](DEPLOY.md) for local runs and Fly.io deployment.

## Repository map

- `app/` — FastAPI pages, night runner, gateway, simulated portal, store, eval harness.
- `cases/` — the 12 evaluation case files.
- `data/` — bundled run exports replayed by the front door.
- `docs/` — generated model instruction text.
- `fixtures/` — the fictional supplier world, all rendered in-repo.
- `logs/` — request/response log lines (no secrets).
- `prompts/` — the exact prompt files that drove Muse Code.
- `results/` — evaluation pilot reports and exports.
- `scripts/` — fixture, run, replay and evaluation helpers.
- `tests/` — contract and behaviour tests.
- `AGENTS.md` — the builder brief; `SCENARIO.md` — the hero scenario.
- `BUILDLOG.md` — dated build log; `PROVENANCE.md` — dependencies, assets, authorship.
- `DEPLOY.md` — local runs and deployment; `fly.toml`, `Dockerfile` — Fly.io service.
- `pyproject.toml`, `uv.lock` — Python dependencies.

## License

MIT. See [LICENSE](LICENSE).
