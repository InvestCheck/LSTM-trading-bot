# Resting order placement: deeper line vs refit line (v2 gate, engine flat only)

Both placements simulated bar by bar as the live bot would place them. Confirmed = the engine signalled on the fill bar (scored with the actual fill and the engine's exit); scratched = closed at that bar's close. Costs 2 ticks. One preregistered test: per touch P&L in ATR, refit minus deeper, 2017 to 2026, one sided z 1.64.

| period | placement | touches | confirmed (of engine trades) | scratched | confirmed avgR | fill vs engine (R) | scratch avg (ATR) | per touch (ATR) | ATR/yr |
|---|---|---|---|---|---|---|---|---|---|
| 2008-2016 | deep | 2865 | 2864 of 4807 engine | 1 | +0.0623 | +0.0171 | -0.4431 | +0.1577 | +52.3 |
| 2008-2016 | refit | 3475 | 2864 of 4807 engine | 611 | +0.0790 | +0.0009 | -0.2052 | +0.1373 | +55.3 |
| 2008-2016 | refit minus deeper | | | | | | | -0.0204 (t -0.86) | reference |
| 2017-2026 | deep | 3341 | 3337 of 5436 engine | 4 | +0.0268 | +0.0189 | -0.4454 | -0.0079 | -2.7 |
| 2017-2026 | refit | 4632 | 3340 of 5436 engine | 1292 | +0.0472 | +0.0003 | -0.2066 | -0.0316 | -15.1 |
| 2017-2026 | refit minus deeper | | | | | | | -0.0237 (t -1.04) | no |

fill vs engine: positive means the fill was worse than the engine's assumed entry, in R. Deeper placement should show ~+0.03; refit placement should show ~0 with more scratches.
