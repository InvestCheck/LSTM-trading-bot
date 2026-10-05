# Exit, filter and band fade study on the frozen engine's entries (fill = intrabar)

Entry bar features (EMA distances, momentum, room) are measured at the entry bar's close. With intrabar fills that close comes AFTER the fill, so those filters contain lookahead and are for reference only; the `next` fill run is the decision basis.

Harvested candidates: 25202. Engine trades reproduced exactly by the harness: 17440/17440.

Preregistered tests: 15. One sided Bonferroni threshold on the bootstrap t: **2.71**. Costs: 2 ticks per round trip. Bootstrap: 400 resamples of calendar quarters.

## Exit variants (each on its own non overlapping trade set)

| variant | trades | avgR net | win% | PF | total R | boot t | paired diff vs engine | paired t | verdict |
|---|---|---|---|---|---|---|---|---|---|
| engine | 17443 | +0.0290 | 48.6 | 1.07 | +505 | 2.63 | | | reference |
| engine_noparab | 14190 | -0.0118 | 36.1 | 0.98 | -167 | -0.65 | -0.0340 (13815 paired) | -3.36 | worse |
| target_2R | 11554 | +0.0404 | 36.4 | 1.06 | +467 | 2.04 | +0.0220 (11217 paired) | 1.67 | no |
| half_at_1R | 17443 | +0.0205 | 56.0 | 1.05 | +358 | 2.13 | -0.0084 (17443 paired) | -3.74 | worse |
| chandelier_3atr | 16674 | +0.0434 | 35.8 | 1.10 | +723 | 2.40 | +0.0243 (14674 paired) | 1.99 | no |
| time_48 | 14982 | +0.0437 | 37.3 | 1.08 | +655 | 1.74 | +0.0262 (13736 paired) | 1.41 | no |

## Filters on the engine's trades (in vs out)

| filter | rule | in: n, avgR, win% | out: n, avgR, win% | diff | boot t | verdict |
|---|---|---|---|---|---|---|
| room_ge_0.5 | room >= 0.5 | 14835, +0.0507, 48% | 2608, -0.0945, 50% | +0.1451 | 7.86 | PASS |
| room_ge_1.0 | room >= 1.0 | 12582, +0.0607, 46% | 4861, -0.0530, 55% | +0.1137 | 6.13 | PASS |
| above_e21 | d_e21 >= 0.0 | 17145, +0.0436, 49% | 298, -0.8142, 12% | +0.8578 | 22.40 | PASS |
| above_e200 | d_e200 >= 0.0 | 17286, +0.0335, 49% | 157, -0.4723, 25% | +0.5058 | 4.91 | PASS |
| no_fade_20bar | mom20 >= -1.0 | 17317, +0.0354, 49% | 126, -0.8519, 10% | +0.8873 | 16.25 | PASS |
| near_1y_extreme | ext_1y >= -3.0 | 2100, +0.0455, 51% | 15343, +0.0267, 48% | +0.0188 | 0.63 | no |
| calm_atr | atr_ratio <= 1.5 | 16076, +0.0215, 48% | 1367, +0.1174, 54% | -0.0960 | -2.79 | no |
| ny_session | hour in (8, 16) | 8947, +0.0509, 49% | 8496, +0.0059, 48% | +0.0451 | 2.41 | no |

## Band fade (trade against breaks that fire with little room to the band; 2 tick cost charged, one fade at a time per instrument)

| room threshold | fade trades | avgR | win% | PF | boot t | verdict | (engine avgR on same signals) |
|---|---|---|---|---|---|---|---|
| room < 0.5 | 2571 | -0.0618 | 30.0 | 0.90 | -1.57 | no | -0.0949 on 2571 |
| room < 0.0 | 1272 | -0.0818 | 25.1 | 0.85 | -1.77 | no | -0.1556 on 1272 |

## Resting order model (fill at the line, scratch at that bar's close if the engine does not confirm)

naive = a stop order on every line that could be touched; prequalified = only lines whose refit geometry and stop already pass on data through the previous bar. All P&L in ATR units, net of 2 ticks.

| model | touches | confirmed | confirmed avg (ATR) | scratched avg (ATR) | **per touch (ATR)** | total (ATR) |
|---|---|---|---|---|---|---|
| naive | 47675 | 17442 (37%) | +0.0583 | -0.0479 | -0.0090 | -431 |
| prequalified | 17606 | 17380 (99%) | +0.0632 | -0.0754 | +0.0614 | +1081 |

The confirmed trades are the engine's own trades, scored at the line. A positive per touch number means resting orders recover the intrabar edge after paying for the scratches.


## Feature summary on the engine's trades (avgR by quartile)

| feature | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---|---|---|---|
| room | -0.060 (n=4361) | +0.003 (n=4362) | +0.018 (n=4359) | +0.155 (n=4361) |
| d_e21 | -0.268 (n=4361) | +0.012 (n=4362) | +0.130 (n=4359) | +0.242 (n=4361) |
| d_e50 | -0.203 (n=4361) | +0.049 (n=4361) | +0.116 (n=4360) | +0.154 (n=4361) |
| d_e200 | -0.069 (n=4361) | +0.060 (n=4361) | +0.071 (n=4360) | +0.054 (n=4361) |
| mom5 | -0.212 (n=4361) | -0.006 (n=4361) | +0.114 (n=4360) | +0.221 (n=4361) |
| mom20 | -0.165 (n=4361) | +0.061 (n=4361) | +0.119 (n=4360) | +0.100 (n=4361) |
| ext_1y | -0.006 (n=4361) | +0.030 (n=4361) | +0.030 (n=4360) | +0.062 (n=4361) |
| ext_5y | -0.024 (n=4361) | +0.052 (n=4361) | +0.051 (n=4360) | +0.038 (n=4361) |
| atr_ratio | -0.041 (n=4363) | +0.018 (n=4359) | +0.034 (n=4360) | +0.105 (n=4361) |
| risk_atr | +0.075 (n=4362) | +0.020 (n=4360) | +0.022 (n=4360) | -0.000 (n=4361) |
| touches | +0.027 (n=11830) | n/a | +0.031 (n=3346) | +0.038 (n=2267) |
| span | +0.033 (n=4367) | +0.021 (n=4356) | +0.012 (n=4359) | +0.050 (n=4361) |
