# Grounding probe

Effort: medium · runs: 10 · passed: 7 · verdict: **FAIL**
Cost: $0.0366 · model: muse-spark-1.3 · 2026-10-28

Line: `Delivery: Goods will leave our warehouse by 10 November.`
Band (PNG pixels): {'text': 'Delivery: Goods will leave our warehouse by 10 November.', 'y_top': 311, 'y_bottom': 333, 'x_left': 66, 'x_right': 384} · PNG size: [595, 841]

| run | bbox (0-1000) | centre y (px) | coverage | pass | seconds |
|---|---|---|---|---|---|
| 1 | 107,382,592,400 | 328.8 | 0.900 | PASS | 7.62 |
| 2 | 109,382,688,399 | 328.4 | 1.000 | PASS | 4.36 |
| 3 | 109,382,689,401 | 329.3 | 1.000 | PASS | 5.78 |
| 4 | 107,419,690,433 | 358.3 | 1.000 | FAIL | 4.67 |
| 5 | 108,382,688,399 | 328.4 | 1.000 | PASS | 3.87 |
| 6 | 109,352,642,370 | 303.6 | 0.994 | FAIL | 4.35 |
| 7 | 110,350,690,370 | 302.8 | 1.000 | FAIL | 3.76 |
| 8 | 108,383,690,399 | 328.8 | 1.000 | PASS | 4.18 |
| 9 | 108,382,643,399 | 328.4 | 0.996 | PASS | 5.87 |
| 10 | 108,382,688,400 | 328.8 | 1.000 | PASS | 5.64 |

Verdict: 7 of 10 on target — FAIL
(pass mark: 9 of 10).
