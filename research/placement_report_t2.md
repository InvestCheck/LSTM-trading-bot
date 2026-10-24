# Resting order placement: deeper line, refit line, and gap aware hybrids (v2 gate, engine flat only)


Minimum touches for this run: 2.

Placements simulated bar by bar as the live bot would place them. Confirmed = the engine signalled on the fill bar (scored with the actual fill and the engine's exit); scratched = closed at that bar's close. Costs 2 ticks. hyb_K = refit line when the lines are more than K R apart, else the deeper line.

| period | placement | touches | confirmed (of engine trades) | scratched | confirmed avgR | fill vs engine (R) | worst fill vs engine (R) | scratch avg (ATR) | per touch (ATR) | ATR/yr |
|---|---|---|---|---|---|---|---|---|---|---|
| 2008-2016 | deep | 5117 | 5117 of 10716 engine | 0 | +0.0538 | +0.0090 | +2.25 | +0.0000 | +0.1752 | +103.9 |
| 2008-2016 | refit | 5726 | 5117 of 10716 engine | 609 | +0.0637 | +0.0002 | +1.30 | -0.1835 | +0.1648 | +109.3 |
| 2008-2016 | hyb_0.1 | 5665 | 5117 of 10716 engine | 548 | +0.0602 | +0.0020 | +1.36 | -0.1485 | +0.1621 | +106.4 |
| 2008-2016 | hyb_0.25 | 5574 | 5117 of 10716 engine | 457 | +0.0594 | +0.0034 | +1.36 | -0.1199 | +0.1662 | +107.3 |
| 2008-2016 | hyb_0.5 | 5466 | 5117 of 10716 engine | 349 | +0.0566 | +0.0060 | +1.36 | -0.0912 | +0.1661 | +105.1 |
| 2017-2026 | deep | 5721 | 5718 of 11095 engine | 3 | +0.0337 | +0.0115 | +2.71 | -0.0855 | +0.0593 | +35.0 |
| 2017-2026 | refit | 7006 | 5719 of 11095 engine | 1287 | +0.0449 | +0.0005 | +1.16 | -0.2007 | +0.0329 | +23.8 |
| 2017-2026 | hyb_0.1 | 6898 | 5719 of 11095 engine | 1179 | +0.0424 | +0.0028 | +1.16 | -0.1764 | +0.0351 | +25.0 |
| 2017-2026 | hyb_0.25 | 6788 | 5719 of 11095 engine | 1069 | +0.0401 | +0.0052 | +1.56 | -0.1495 | +0.0365 | +25.6 |
| 2017-2026 | hyb_0.5 | 6594 | 5718 of 11095 engine | 876 | +0.0373 | +0.0077 | +1.56 | -0.1452 | +0.0382 | +26.0 |

## By gap between the lines, 2017 to 2026 (per touch ATR; n = touches)

| gap (R) | deep | refit | hyb_0.1 | hyb_0.25 | hyb_0.5 |
|---|---|---|---|---|---|
| 0 to 0.05 | +0.072 (n=5489) | +0.066 (n=5480) | +0.066 (n=5418) | +0.070 (n=5437) | +0.071 (n=5453) |
| 0.05 to 0.1 | -0.276 (n=85) | -0.157 (n=137) | -0.210 (n=82) | -0.242 (n=83) | -0.242 (n=83) |
| 0.1 to 0.25 | -0.627 (n=76) | -0.147 (n=204) | -0.149 (n=207) | -0.633 (n=75) | -0.633 (n=75) |
| 0.25 to 0.5 | +0.364 (n=41) | +0.024 (n=246) | +0.040 (n=249) | +0.040 (n=250) | +0.195 (n=39) |
| 0.5 to 1.0 | +0.129 (n=23) | -0.046 (n=293) | -0.040 (n=294) | -0.040 (n=294) | -0.040 (n=294) |
| 1.0 to 99 | -0.797 (n=7) | -0.111 (n=646) | -0.099 (n=648) | -0.099 (n=649) | -0.095 (n=650) |

## Preregistered test

Best hybrid on 2008 to 2016: **hyb_0.25** (per touch -0.0090 ATR vs deep, t -0.91).
Holdout 2017 to 2026, hyb_0.25 minus deep: **-0.0228 ATR per touch, t -2.23 -> no** (z 1.64).
For reference, refit minus deep on the holdout: -0.0263 (t -2.10).

fill vs engine: positive means the fill was worse than the engine's assumed entry, in R; the worst column is the tail the deeper line placement carries (E1 on 2026-10-14 was +1.37R).
