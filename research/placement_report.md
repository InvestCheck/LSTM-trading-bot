# Resting order placement: deeper line, refit line, and gap aware hybrids (v2 gate, engine flat only)

Placements simulated bar by bar as the live bot would place them. Confirmed = the engine signalled on the fill bar (scored with the actual fill and the engine's exit); scratched = closed at that bar's close. Costs 2 ticks. hyb_K = refit line when the lines are more than K R apart, else the deeper line.

| period | placement | touches | confirmed (of engine trades) | scratched | confirmed avgR | fill vs engine (R) | worst fill vs engine (R) | scratch avg (ATR) | per touch (ATR) | ATR/yr |
|---|---|---|---|---|---|---|---|---|---|---|
| 2008-2016 | deep | 2865 | 2864 of 4807 engine | 1 | +0.0623 | +0.0171 | +2.25 | -0.4431 | +0.1577 | +52.3 |
| 2008-2016 | refit | 3475 | 2864 of 4807 engine | 611 | +0.0790 | +0.0009 | +1.30 | -0.2052 | +0.1373 | +55.3 |
| 2008-2016 | hyb_0.1 | 3411 | 2864 of 4807 engine | 547 | +0.0732 | +0.0049 | +1.36 | -0.1656 | +0.1336 | +52.8 |
| 2008-2016 | hyb_0.25 | 3320 | 2864 of 4807 engine | 456 | +0.0716 | +0.0076 | +1.36 | -0.1359 | +0.1403 | +54.0 |
| 2008-2016 | hyb_0.5 | 3216 | 2864 of 4807 engine | 352 | +0.0670 | +0.0120 | +1.36 | -0.0960 | +0.1428 | +53.2 |
| 2017-2026 | deep | 3341 | 3337 of 5436 engine | 4 | +0.0268 | +0.0189 | +2.71 | -0.4454 | -0.0079 | -2.7 |
| 2017-2026 | refit | 4632 | 3340 of 5436 engine | 1292 | +0.0472 | +0.0003 | +0.56 | -0.2066 | -0.0316 | -15.1 |
| 2017-2026 | hyb_0.1 | 4517 | 3340 of 5436 engine | 1177 | +0.0415 | +0.0047 | +0.60 | -0.1806 | -0.0301 | -14.0 |
| 2017-2026 | hyb_0.25 | 4398 | 3339 of 5436 engine | 1059 | +0.0377 | +0.0087 | +1.56 | -0.1504 | -0.0259 | -11.8 |
| 2017-2026 | hyb_0.5 | 4211 | 3337 of 5436 engine | 874 | +0.0327 | +0.0130 | +1.56 | -0.1414 | -0.0262 | -11.4 |

## By gap between the lines, 2017 to 2026 (per touch ATR; n = touches)

| gap (R) | deep | refit | hyb_0.1 | hyb_0.25 | hyb_0.5 |
|---|---|---|---|---|---|
| 0 to 0.05 | +0.007 (n=3097) | +0.003 (n=3113) | +0.005 (n=3042) | +0.005 (n=3054) | +0.007 (n=3061) |
| 0.05 to 0.1 | -0.324 (n=98) | -0.159 (n=150) | -0.269 (n=95) | -0.296 (n=96) | -0.296 (n=96) |
| 0.1 to 0.25 | -0.539 (n=75) | -0.318 (n=204) | -0.318 (n=207) | -0.542 (n=73) | -0.542 (n=73) |
| 0.25 to 0.5 | +0.555 (n=43) | +0.087 (n=232) | +0.103 (n=235) | +0.102 (n=236) | +0.404 (n=41) |
| 0.5 to 1.0 | +0.318 (n=21) | -0.048 (n=281) | -0.053 (n=283) | -0.053 (n=283) | -0.053 (n=283) |
| 1.0 to 99 | -0.797 (n=7) | -0.114 (n=652) | -0.105 (n=655) | -0.105 (n=656) | -0.101 (n=657) |

## Preregistered test

Best hybrid on 2008 to 2016: **hyb_0.5** (per touch -0.0150 ATR vs deep, t -0.94).
Holdout 2017 to 2026, hyb_0.5 minus deep: **-0.0183 ATR per touch, t -1.06 -> no** (z 1.64).
For reference, refit minus deep on the holdout: -0.0237 (t -1.04).

fill vs engine: positive means the fill was worse than the engine's assumed entry, in R; the worst column is the tail the deeper line placement carries (E1 on 2026-10-14 was +1.37R).
