# Grounding probe

Effort: low · runs: 10 · passed: 2 · verdict: **FAIL**
Cost: $0.0221 · model: muse-spark-1.3 · 2026-10-28

Line: `Delivery: Goods will leave our warehouse by 10 November.`
Band (PNG pixels): {'text': 'Delivery: Goods will leave our warehouse by 10 November.', 'y_top': 311, 'y_bottom': 333, 'x_left': 66, 'x_right': 384} · PNG size: [595, 841]

| run | bbox (0-1000) | centre y (px) | coverage | pass | seconds |
|---|---|---|---|---|---|
| 1 | 108,351,692,369 | 302.8 | 1.000 | FAIL | 3.33 |
| 2 | 108,351,643,369 | 302.8 | 0.996 | FAIL | 3.09 |
| 3 | 108,382,690,399 | 328.4 | 1.000 | PASS | 3.87 |
| 4 | 108,354,642,370 | 304.4 | 0.994 | FAIL | 3.16 |
| 5 | 108,353,690,370 | 304.0 | 1.000 | FAIL | 4.92 |
| 6 | 108,350,645,369 | 302.3 | 0.999 | FAIL | 4.02 |
| 7 | 108,351,688,368 | 302.3 | 1.000 | FAIL | 4.38 |
| 8 | 108,351,689,369 | 302.8 | 1.000 | FAIL | 3.24 |
| 9 | 107,382,689,399 | 328.4 | 1.000 | PASS | 4.27 |
| 10 | 110,350,645,370 | 302.8 | 0.999 | FAIL | 2.55 |

Verdict: 2 of 10 on target — FAIL
(pass mark: 9 of 10).
