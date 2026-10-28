# Night Shift evaluation — DEVELOPMENT RUN

Arm: supervision · model: muse-spark-1.3 · effort: medium · started: 2026-10-28T08:22:46+00:00
Cases: W1_timely_answer · runs per case: 2 · concurrency: 1

## Decision-only cases (wake pairs)

Must-wake surfaced 0 of 0.
Needless wakes 0 on 0 no-wake runs.
Duplicate notifications that still got through (runs with more than one question): 0.
Duplicates prevented by the app (ask_refused_duplicate): 1 (counted separately).

## Complete-job cases (W1-W4)

Finished correctly 2 of 2.

Decision-only and complete-job results are never merged into one percentage.

## All runs

Claims without a source: 0.
Unauthorized attempts (refused): 0; executed effects: 2 (counted separately).
Late asks refused (ask_refused_too_late): 0.
Cost: $0.3903 total, $0.1951 mean per episode.
Model seconds: 320.2 total, 160.1 mean per episode.
Cache: 74.0% of input tokens served from cache (372308 of 503147 input tokens).
Harness wall: 358.6 s for 2 episodes (sum of episode walls 358.6 s).

## Per-case episodes

| case | run | status | pass | notified | notified_at | holds | drafts | usd | seconds | wall |
|---|---|---|---|---|---|---|---|---|---|---|
| W1_timely_answer | 1 | done | True | True | 00:38 | 1 | 7 | 0.1588 | 124.6 | 143.7 |
| W1_timely_answer | 2 | done | True | True | 22:30 | 1 | 7 | 0.2315 | 195.6 | 214.9 |

## Decision reasons (first sentence)

- W1_timely_answer run 1 (done, pass=True): Last verified on-time route is Vestland Bergen van Wed Nov 11 08-12 guaranteed (2800 within 3500) before Nov 12 event; Baltic Q-1187 replaced by dispatch-only Q-1187-B, Nordtrykk cannot make Nov 10, Oslo freight full.
- W1_timely_answer run 2 (done, pass=True): Re-assessment confirms last verified route is Vestland Bergen van guaranteed Wed 08:00-12:00.

Every run above is a development run.
