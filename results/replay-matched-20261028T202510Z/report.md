# Matched replay experiment — DEVELOPMENT RUN

Recorded night: 6c7c7c742513 at its paused state (after the question, before the answer); same owner answer 'Bergen: the venue can receive it' at 01:05 in every fork.
Arm replay resumes exactly as the app does (encrypted reasoning replayed, documents not re-sent); arm resend drops the reasoning items and re-attaches the read-turn plus reassess-turn source content (both PDFs by fresh file id, texts inline).
Model: muse-spark-1.3 · effort: medium · started: 2026-10-28T20:25:10+00:00

## Means per arm (3 runs each)

| arm | mean input | mean cached | mean output | mean s | mean $ | holds | mean drafts | thanks-venue runs |
|---|---|---|---|---|---|---|---|---|
| replay | 53252.7 | 46868.3 | 9222.7 | 48.2 | 0.0542 | 3/3 | 5.0 | 2/3 |
| resend | 132037.3 | 113114.7 | 6676.3 | 46.3 | 0.069 | 3/3 | 5.0 | 3/3 |

## Runs

| arm | rep | job | status | in | cached | out | hold | drafts | thanks | usd | s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| replay | 1 | 2edfca5e5ced | done | 33401 | 20706 | 6501 | True | 5 | 3 | 0.0466 | 32.6 |
| replay | 2 | a043385718b0 | done | 93000 | 89352 | 11593 | True | 5 | 0 | 0.0672 | 70.7 |
| replay | 3 | 0c8c4ad92b97 | done | 33357 | 30547 | 9574 | True | 5 | 3 | 0.0488 | 41.4 |
| resend | 1 | d9a8bbd51816 | done | 154418 | 129446 | 6743 | True | 5 | 1 | 0.0793 | 47.0 |
| resend | 2 | 017885fac8a0 | done | 83511 | 76996 | 6133 | True | 5 | 1 | 0.0458 | 37.6 |
| resend | 3 | 5f2aa871d986 | done | 158183 | 132902 | 7153 | True | 5 | 2 | 0.0819 | 54.3 |

Every run above is a development run.
