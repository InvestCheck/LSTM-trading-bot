# Confluence filters on the engine's trades (features on the bar before entry, no lookahead)

17443 engine trades. in = trades the filter keeps. One preregistered test: best filter on 2008 to 2016 by in minus out t, tested on 2017 to 2026 (z 1.64, keep at least 25%).

| set | filter | in: n, avgR, win% | out: n, avgR, win% | in minus out | boot t | kept |
|---|---|---|---|---|---|---|
| explore 2008-2016 | adx_ge_20 | 5380, +0.0063, 49% | 2441, +0.0578, 46% | -0.0514 | -1.89 | 69% |
| explore 2008-2016 | adx_ge_25 | 3980, -0.0070, 50% | 3841, +0.0528, 46% | -0.0599 | -2.34 | 51% |
| explore 2008-2016 | adx_le_20 | 2443, +0.0572, 46% | 5378, +0.0065, 49% | +0.0507 | 1.86 | 31% |
| explore 2008-2016 | macd_aligned | 4679, +0.0082, 50% | 3142, +0.0434, 46% | -0.0352 | -1.63 | 60% |
| explore 2008-2016 | rsi_aligned | 7501, +0.0158, 48% | 320, +0.1775, 51% | -0.1618 | -2.74 | 96% |
| explore 2008-2016 | e50_slope_aligned | 7079, +0.0172, 47% | 742, +0.0721, 54% | -0.0549 | -1.48 | 91% |
| explore 2008-2016 | htf_aligned | 7199, +0.0199, 48% | 622, +0.0504, 47% | -0.0304 | -0.69 | 92% |
| explore 2008-2016 | breadth_ge_1 | 5926, +0.0358, 49% | 1895, -0.0197, 46% | +0.0555 | 1.77 | 76% |
| explore 2008-2016 | cluster_ge_1 | 4120, +0.0369, 49% | 3701, +0.0062, 47% | +0.0307 | 1.12 | 53% |
| explore 2008-2016 | adx20_macd_rsi | 3023, -0.0120, 51% | 4798, +0.0440, 46% | -0.0560 | -2.34 | 39% |
| holdout 2017-2026 | adx_ge_20 | 6816, +0.0196, 49% | 2806, +0.0702, 49% | -0.0507 | -2.22 | 71% |
| holdout 2017-2026 | adx_ge_25 | 5140, +0.0189, 50% | 4482, +0.0520, 48% | -0.0331 | -1.37 | 53% |
| holdout 2017-2026 | adx_le_20 | 2811, +0.0701, 49% | 6811, +0.0196, 49% | +0.0504 | 2.19 | 29% |
| holdout 2017-2026 | macd_aligned | 6030, +0.0380, 51% | 3592, +0.0282, 45% | +0.0099 | 0.37 | 63% |
| holdout 2017-2026 | rsi_aligned | 9252, +0.0279, 49% | 370, +0.1960, 53% | -0.1682 | -2.99 | 96% |
| holdout 2017-2026 | e50_slope_aligned | 8724, +0.0306, 48% | 898, +0.0705, 56% | -0.0399 | -0.94 | 91% |
| holdout 2017-2026 | htf_aligned | 8724, +0.0360, 49% | 898, +0.0185, 47% | +0.0174 | 0.48 | 91% |
| holdout 2017-2026 | breadth_ge_1 | 7393, +0.0275, 49% | 2229, +0.0571, 51% | -0.0296 | -1.12 | 77% |
| holdout 2017-2026 | cluster_ge_1 | 5454, +0.0243, 48% | 4168, +0.0475, 51% | -0.0233 | -1.02 | 57% |
| holdout 2017-2026 | adx20_macd_rsi | 3998, +0.0269, 52% | 5624, +0.0396, 47% | -0.0127 | -0.60 | 42% |

## Feature summary, holdout (avgR by quartile of the continuous features; sign features by value)

- adx: Q1 +0.080 (n=2410), Q2 +0.032 (n=2405), Q3 +0.044 (n=2402), Q4 -0.020 (n=2405)
- breadth: Q1 +0.041 (n=4120), Q2 +0.077 (n=1580), Q3 +0.044 (n=2045), Q4 -0.026 (n=1877)
- cluster: Q1 +0.048 (n=4168), Q2 +0.030 (n=2113), Q3 +0.060 (n=1353), Q4 -0.006 (n=1988)
- macd: aligned +0.038 (n=6030), against +0.028 (n=3592)
- rsi: aligned +0.028 (n=9252), against +0.196 (n=370)
- e50_slope: aligned +0.031 (n=8724), against +0.071 (n=898)
- htf: aligned +0.036 (n=8724), against +0.019 (n=898)

## Preregistered test

Best on exploration: **adx_le_20** (t 1.86).
Holdout in minus out: **+0.0504R, t 2.19, keeps 29% -> PASS**.
