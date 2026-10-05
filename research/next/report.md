# Exit, filter and band fade study on the frozen engine's entries (fill = next)

Entry bar features (EMA distances, momentum, room) are measured at the entry bar's close. With next bar fills the close is known before the fill, so the filters are usable live.

Harvested candidates: 25175. Trigger: intrabar touch (as the live bot runs it), fill: next bar open. The harvest is validated by the intrabar run's self check.

Preregistered tests: 15. One sided Bonferroni threshold on the bootstrap t: **2.71**. Costs: 2 ticks per round trip. Bootstrap: 400 resamples of calendar quarters.

## Exit variants (each on its own non overlapping trade set)

| variant | trades | avgR net | win% | PF | total R | boot t | paired diff vs engine | paired t | verdict |
|---|---|---|---|---|---|---|---|---|---|
| engine | 17218 | -0.0414 | 44.9 | 0.90 | -713 | -4.51 | | | reference |
| engine_noparab | 13713 | -0.0890 | 33.7 | 0.82 | -1220 | -5.92 | -0.0452 (13343 paired) | -5.06 | worse |
| target_2R | 10918 | -0.0108 | 34.6 | 0.98 | -118 | -0.56 | +0.0344 (10611 paired) | 2.48 | no |
| half_at_1R | 17218 | -0.0363 | 52.2 | 0.91 | -625 | -4.34 | +0.0051 (17218 paired) | 2.41 | no |
| chandelier_3atr | 16431 | -0.0063 | 33.9 | 0.98 | -103 | -0.40 | +0.0343 (14409 paired) | 2.96 | PASS |
| time_48 | 14800 | -0.0013 | 37.1 | 1.00 | -19 | -0.06 | +0.0372 (13481 paired) | 2.23 | no |

## Filters on the engine's trades (in vs out)

| filter | rule | in: n, avgR, win% | out: n, avgR, win% | diff | boot t | verdict |
|---|---|---|---|---|---|---|
| room_ge_0.5 | room >= 0.5 | 13294, -0.0403, 44% | 3924, -0.0450, 48% | +0.0046 | 0.39 | no |
| room_ge_1.0 | room >= 1.0 | 10747, -0.0517, 41% | 6471, -0.0242, 52% | -0.0275 | -2.18 | no |
| above_e21 | d_e21 >= 0.0 | 16951, -0.0389, 45% | 267, -0.1998, 35% | +0.1609 | 2.84 | PASS |
| above_e200 | d_e200 >= 0.0 | 17089, -0.0396, 45% | 129, -0.2835, 34% | +0.2439 | 1.77 | no |
| no_fade_20bar | mom20 >= -1.0 | 17109, -0.0402, 45% | 109, -0.2212, 37% | +0.1810 | 1.70 | no |
| near_1y_extreme | ext_1y >= -3.0 | 2127, -0.0197, 46% | 15091, -0.0444, 45% | +0.0247 | 0.80 | no |
| calm_atr | atr_ratio <= 1.5 | 15859, -0.0469, 45% | 1359, +0.0225, 46% | -0.0693 | -2.73 | no |
| ny_session | hour in (8, 16) | 8850, -0.0399, 45% | 8368, -0.0430, 45% | +0.0031 | 0.18 | no |

## Band fade (trade against breaks that fire with little room to the band; 2 tick cost charged, one fade at a time per instrument)

| room threshold | fade trades | avgR | win% | PF | boot t | verdict | (engine avgR on same signals) |
|---|---|---|---|---|---|---|---|
| room < 0.5 | 3881 | -0.0705 | 25.3 | 0.90 | -2.43 | no | -0.0431 on 3881 |
| room < 0.0 | 2094 | -0.0724 | 20.2 | 0.89 | -1.65 | no | -0.0840 on 2094 |

## Feature summary on the engine's trades (avgR by quartile)

| feature | Q1 (low) | Q2 | Q3 | Q4 (high) |
|---|---|---|---|---|
| room | -0.038 (n=4305) | -0.011 (n=4305) | -0.014 (n=4303) | -0.103 (n=4305) |
| d_e21 | -0.092 (n=4305) | -0.027 (n=4304) | -0.013 (n=4304) | -0.034 (n=4305) |
| d_e50 | -0.076 (n=4306) | -0.021 (n=4303) | -0.019 (n=4304) | -0.049 (n=4305) |
| d_e200 | -0.037 (n=4305) | -0.020 (n=4304) | -0.056 (n=4304) | -0.052 (n=4305) |
| mom5 | -0.069 (n=4305) | -0.034 (n=4304) | -0.019 (n=4304) | -0.044 (n=4305) |
| mom20 | -0.080 (n=4305) | -0.041 (n=4305) | -0.007 (n=4303) | -0.038 (n=4305) |
| ext_1y | -0.066 (n=4305) | -0.036 (n=4304) | -0.042 (n=4304) | -0.021 (n=4305) |
| ext_5y | -0.069 (n=4305) | -0.035 (n=4304) | -0.026 (n=4304) | -0.035 (n=4305) |
| atr_ratio | -0.058 (n=4305) | -0.039 (n=4305) | -0.051 (n=4304) | -0.017 (n=4304) |
| risk_atr | -0.119 (n=4305) | -0.011 (n=4305) | -0.019 (n=4303) | -0.016 (n=4305) |
| touches | -0.029 (n=11742) | n/a | -0.056 (n=3285) | -0.086 (n=2191) |
| span | -0.061 (n=4308) | -0.040 (n=4301) | -0.055 (n=4304) | -0.010 (n=4305) |
