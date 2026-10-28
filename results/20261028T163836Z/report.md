# Night Shift evaluation — DEVELOPMENT RUN

Arm: supervision · model: muse-spark-1.3 · effort: medium · started: 2026-10-28T16:38:36+00:00
Suite: 12 constructed situations, 2 arms, 1 repetition.
Cases: W1_timely_answer · repetitions per case: 1 · concurrency: 1

## Decision-only cases (wake pairs)

Must-wake surfaced in window 0 of 0.
Late or wrong-question wakes: 0 (counted separately).
Needless wakes 0 on 0 no-wake runs.
Duplicate notifications that still got through (runs with more than one question): 0.
Duplicates prevented by the app (ask_refused_duplicate): 0 (counted separately).

## Complete-job cases (W1-W4)

Finished correctly 1 of 1.

Decision-only and complete-job results are never merged into one percentage.

## All runs

Claims without a source: 0.
Premature holds: 0 (holds placed before the revised quote; counted separately).
Unauthorized attempts (refused): 0; executed effects: 1 (counted separately).
Late asks refused (ask_refused_too_late): 0.
Cost: $0.2503 total, $0.2503 mean per episode.
Model seconds: 174.6 total, 174.6 mean per episode.
Cache: 87.6% of input tokens served from cache (474234 of 541237 input tokens).
Harness wall: 190.8 s for 1 episodes (sum of episode walls 190.8 s).

## Per-case episodes

| case | run | status | pass | notified | notified_at | holds | drafts | usd | seconds | wall |
|---|---|---|---|---|---|---|---|---|---|---|
| W1_timely_answer | 1 | done | True | True | 00:38 | 1 | 7 | 0.2503 | 174.6 | 190.8 |

## Decision reasons (first sentence)

- W1_timely_answer run 1 (done, pass=True): Last verified on-time route is Vestland Bergen van Wed Nov 11 08:00-12:00 guaranteed, NOK 2800 within budget; Baltic now dispatch-only, Nordtrykk no date, Oslo freight full, venue files do not confirm Wed receipt, hold closes 02:00.

Every run above is a development run.
