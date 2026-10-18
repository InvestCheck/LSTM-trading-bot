# VWAP band fades on 1, 5 and 15 minute bars (CME micro universe)

Session VWAP anchored at 18:00 ET; all levels taken from the previous bar's close. Family A: limit fade at the 3 band, stop 4.5 band, target VWAP. Family B: rejection bar at the 2 band, next open entry, stop beyond the bar, target VWAP. Flat 16:45 ET. Costs $1.5 per side plus a tick on stop and time exits. Per family the timeframe with the best exploration net avgR is the one tested on the holdout; two tests, PASS = net avgR > 0 and monthly block bootstrap t > 2.0.


## band3_limit

| set | trades | per session | net avgR | boot t | win% | PF | daily Sharpe (ann.) |
|---|---|---|---|---|---|---|---|
| 1m explore 2008-2016 | 33872 | 14.57 | -0.2743 | -30.38 | 39% | 0.64 | -0.80 |
| 5m explore 2008-2016 | 46919 | 20.16 | -0.2883 | -33.75 | 39% | 0.63 | -1.65 |
| 15m explore 2008-2016 | 61145 | 26.27 | -0.3183 | -40.73 | 38% | 0.60 | -1.47 |
| 1m holdout 2017-2026 (THE TEST) | 35787 | 14.33 | -0.2660 | -27.76 | 38% | 0.66 | -1.79 |
| 5m holdout 2017-2026 | 46294 | 18.52 | -0.2849 | -29.40 | 38% | 0.64 | -2.37 |
| 15m holdout 2017-2026 | 58430 | 23.35 | -0.3060 | -36.33 | 37% | 0.62 | -2.35 |

**band3_limit at 1m: holdout net avgR -0.2660, t -27.76 -> no**
- exits by target: 12347 (35%), avgR +1.417
- exits by stop: 21340 (60%), avgR -1.280
- exits by time: 2100 (6%), avgR +0.137

Per instrument on the holdout at the tested timeframe:

| instrument | trades | per session | net avgR | boot t | win% | PF | daily Sharpe |
|---|---|---|---|---|---|---|---|
| ES | 2821 | 1.70 | -0.2090 | -8.92 | 38% | 0.72 | -1.81 |
| NQ | 3002 | 1.78 | -0.1252 | -5.20 | 38% | 0.82 | -0.64 |
| RTY | 2802 | 1.69 | -0.1991 | -7.64 | 40% | 0.73 | -1.56 |
| GC | 2694 | 1.65 | -0.1343 | -5.72 | 38% | 0.80 | -0.75 |
| SI | 2495 | 1.59 | -0.1059 | -3.59 | 39% | 0.84 | -0.85 |
| HG | 2036 | 1.47 | -0.2365 | -8.69 | 36% | 0.68 | -2.00 |
| CL | 3107 | 1.81 | -0.3252 | -15.18 | 38% | 0.60 | -3.22 |
| NG | 3747 | 1.90 | -0.0821 | -4.40 | 39% | 0.88 | -0.21 |
| E6 | 2981 | 1.71 | -0.3466 | -14.20 | 38% | 0.58 | -3.81 |
| A6 | 1523 | 1.35 | -0.4183 | -12.28 | 37% | 0.51 | -4.27 |
| B6 | 3319 | 1.82 | -0.6015 | -23.14 | 37% | 0.40 | -6.51 |
| J1 | 2159 | 1.54 | -0.3563 | -13.66 | 37% | 0.56 | -3.71 |
| E1 | 3101 | 1.75 | -0.3662 | -14.41 | 37% | 0.57 | -4.22 |

## band2_reject

| set | trades | per session | net avgR | boot t | win% | PF | daily Sharpe (ann.) |
|---|---|---|---|---|---|---|---|
| 1m explore 2008-2016 | 110208 | 47.38 | -373256158.6499 | -0.90 | 20% | 0.53 | -1.11 |
| 5m explore 2008-2016 | 97802 | 42.03 | -589128318.1680 | -2.25 | 31% | 0.05 | -1.70 |
| 15m explore 2008-2016 | 83633 | 35.94 | -208281375.0740 | -0.83 | 37% | 0.38 | -3.14 |
| 1m holdout 2017-2026 | 117130 | 46.81 | -75533615.4085 | -1.85 | 19% | 0.16 | -5.84 |
| 5m holdout 2017-2026 | 104506 | 41.77 | -0.5662 | -47.71 | 29% | 0.49 | -6.04 |
| 15m holdout 2017-2026 | 88605 | 35.41 | -0.4200 | -45.44 | 36% | 0.48 | -6.84 |
