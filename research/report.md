# Exit, filter and band fade study on the frozen engine's entries

Harvested signals: 24245. Engine trades reproduced from the harvest: 17418/17420.

Preregistered tests: 15. One sided Bonferroni threshold on the bootstrap t: **2.71**. Costs: 2 ticks per round trip. Bootstrap: 400 resamples of calendar quarters.

## Exit variants (each on its own non overlapping trade set)

| variant | trades | avgR net | win% | PF | total R | boot t | paired diff vs engine | paired t | verdict |
|---|---|---|---|---|---|---|---|---|---|
| engine | 17431 | +0.0285 | 48.6 | 1.07 | +496 | 2.58 | | | reference |
| engine_noparab | 14189 | -0.0118 | 36.1 | 0.98 | -168 | -0.65 | -0.0339 (13813 paired) | -3.35 | worse |
| target_2R | 11556 | +0.0394 | 36.3 | 1.06 | +455 | 1.99 | +0.0226 (11234 paired) | 1.71 | no |
| half_at_1R | 17431 | +0.0202 | 56.0 | 1.05 | +352 | 2.08 | -0.0083 (17431 paired) | -3.70 | worse |
| chandelier_3atr | 16661 | +0.0438 | 35.8 | 1.11 | +730 | 2.43 | +0.0246 (14671 paired) | 2.00 | no |
| time_48 | 14974 | +0.0436 | 37.3 | 1.08 | +653 | 1.72 | +0.0268 (13733 paired) | 1.43 | no |

## Filters on the engine's trades (in vs out)

| filter | rule | in: n, avgR, win% | out: n, avgR, win% | diff | boot t | verdict |
|---|---|---|---|---|---|---|
| room_ge_0.5 | room >= 0.5 | 14827, +0.0501, 48% | 2604, -0.0945, 50% | +0.1446 | 7.84 | PASS |
| room_ge_1.0 | room >= 1.0 | 12575, +0.0599, 46% | 4856, -0.0528, 55% | +0.1127 | 6.10 | PASS |
| above_e21 | d_e21 >= 0.0 | 17134, +0.0431, 49% | 297, -0.8134, 12% | +0.8565 | 22.35 | PASS |
| above_e200 | d_e200 >= 0.0 | 17275, +0.0330, 49% | 156, -0.4686, 26% | +0.5016 | 4.83 | PASS |
| no_fade_20bar | mom20 >= -1.0 | 17305, +0.0349, 49% | 126, -0.8514, 10% | +0.8863 | 16.28 | PASS |
| near_1y_extreme | ext_1y >= -3.0 | 2100, +0.0455, 51% | 15331, +0.0261, 48% | +0.0194 | 0.65 | no |
| calm_atr | atr_ratio <= 1.5 | 16067, +0.0208, 48% | 1364, +0.1183, 54% | -0.0974 | -2.83 | no |
| ny_session | hour in (8, 16) | 8939, +0.0508, 49% | 8492, +0.0050, 48% | +0.0459 | 2.47 | no |

## Band fade (trade against breaks that fire with little room to the band)

| room threshold | fade trades | avgR | win% | PF | boot t | verdict | (engine avgR on same signals) |
|---|---|---|---|---|---|---|---|
| room < 0.5 | 2649 | +5.3399 | 43.9 | 10.53 | 2.61 | no | -0.0945 on 2604 |
| room < 0.0 | 1287 | +10.8133 | 58.9 | 27.32 | 2.63 | no | -0.1569 on 1287 |

## Feature summary on the engine's trades (avgR by quartile)

| feature | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---|---|---|---|
| room | -0.060 (n=4358) | +0.004 (n=4358) | +0.017 (n=4357) | +0.153 (n=4358) |
| d_e21 | -0.268 (n=4359) | +0.010 (n=4357) | +0.131 (n=4357) | +0.241 (n=4358) |
| d_e50 | -0.202 (n=4358) | +0.048 (n=4360) | +0.115 (n=4355) | +0.154 (n=4358) |
| d_e200 | -0.070 (n=4358) | +0.059 (n=4359) | +0.071 (n=4356) | +0.053 (n=4358) |
| mom5 | -0.212 (n=4358) | -0.007 (n=4358) | +0.114 (n=4357) | +0.218 (n=4358) |
| mom20 | -0.166 (n=4358) | +0.062 (n=4358) | +0.117 (n=4357) | +0.101 (n=4358) |
| ext_1y | -0.008 (n=4358) | +0.030 (n=4358) | +0.030 (n=4357) | +0.061 (n=4358) |
| ext_5y | -0.024 (n=4358) | +0.052 (n=4358) | +0.050 (n=4357) | +0.037 (n=4358) |
| atr_ratio | -0.041 (n=4362) | +0.018 (n=4356) | +0.032 (n=4357) | +0.104 (n=4356) |
| risk_atr | +0.074 (n=4358) | +0.020 (n=4358) | +0.020 (n=4357) | -0.000 (n=4358) |
| touches | +0.027 (n=11832) | n/a | +0.031 (n=3342) | +0.034 (n=2257) |
| span | +0.032 (n=4363) | +0.020 (n=4354) | +0.011 (n=4356) | +0.050 (n=4358) |
