# Trendline engine on intraday bars (CME micro universe)

Same engine as the hourly protocol (intrabar fill, causal, 2 ticks per round trip) plus commissions on the micro contract, span windows scaled to the bar. Per timeframe the window with the best exploration net avgR is tested on the holdout; one test per timeframe, PASS = net avgR > 0 and monthly block bootstrap t > 2.2. Instrument cost cap (2 ticks / median R_px <= 0.1) set on the exploration half.


## 5 minute bars

| window | set | instruments | trades | per instr/yr | net avgR | gross avgR | boot t | win% | overnight | median cost (R) |
|---|---|---|---|---|---|---|---|---|---|---|
| short | explore | 8 | 86655 | 1204 | -0.2201 | -0.0113 | -26.76 | 39% | 9% | 0.056 |
| medium | explore | 11 | 58613 | 592 | -0.1690 | +0.0260 | -21.62 | 43% | 8% | 0.056 |
| long | explore | 12 | 25572 | 237 | -0.1258 | +0.0320 | -14.30 | 46% | 8% | 0.050 |
| short | holdout | 8 | 90225 | 1163 | -0.3051 | -0.0375 | -38.36 | 37% | 11% | 0.069 |
| medium | holdout | 11 | 66534 | 624 | -0.2389 | -0.0093 | -29.49 | 41% | 9% | 0.064 |
| long | holdout (THE TEST) | 12 | 30895 | 265 | -0.2069 | -0.0002 | -21.19 | 44% | 9% | 0.063 |

**5m, long window: holdout net avgR -0.2069, t -21.19 -> no**

| instrument | trades | net avgR | boot t | win% |
|---|---|---|---|---|
| NQ | 2310 | -0.0019 | -0.07 | 49% |
| RTY | 2442 | -0.0948 | -4.12 | 47% |
| GC | 2757 | +0.0081 | 0.41 | 49% |
| SI | 2350 | -0.1180 | -5.91 | 46% |
| HG | 2533 | -0.0870 | -4.12 | 48% |
| CL | 1797 | -0.2552 | -8.57 | 42% |
| NG | 857 | +0.0933 | 2.84 | 53% |
| E6 | 2990 | -0.2515 | -12.90 | 43% |
| A6 | 3204 | -0.4249 | -19.63 | 38% |
| B6 | 3072 | -0.4491 | -16.47 | 36% |
| J1 | 3146 | -0.2076 | -7.06 | 45% |
| E1 | 3437 | -0.3364 | -16.28 | 39% |

## 15 minute bars

| window | set | instruments | trades | per instr/yr | net avgR | gross avgR | boot t | win% | overnight | median cost (R) |
|---|---|---|---|---|---|---|---|---|---|---|
| short | explore | 12 | 44349 | 411 | -0.1357 | -0.0116 | -18.15 | 38% | 26% | 0.043 |
| medium | explore | 13 | 31878 | 272 | -0.0981 | +0.0131 | -11.49 | 42% | 25% | 0.039 |
| long | explore | 13 | 14705 | 126 | -0.0675 | +0.0268 | -6.38 | 46% | 24% | 0.032 |
| short | holdout | 12 | 48013 | 412 | -0.1834 | -0.0268 | -27.67 | 38% | 27% | 0.052 |
| medium | holdout | 13 | 36018 | 286 | -0.1220 | +0.0075 | -16.64 | 42% | 26% | 0.043 |
| long | holdout (THE TEST) | 13 | 17118 | 136 | -0.0959 | +0.0163 | -10.63 | 45% | 26% | 0.036 |

**15m, long window: holdout net avgR -0.0959, t -10.63 -> no**

| instrument | trades | net avgR | boot t | win% |
|---|---|---|---|---|
| ES | 1323 | -0.0701 | -2.44 | 44% |
| NQ | 1177 | +0.0357 | 1.11 | 48% |
| RTY | 1199 | -0.0630 | -2.16 | 46% |
| GC | 1480 | +0.0503 | 1.89 | 48% |
| SI | 1137 | -0.0665 | -2.04 | 45% |
| HG | 1238 | +0.0034 | 0.10 | 48% |
| CL | 784 | -0.1273 | -3.26 | 44% |
| NG | 365 | +0.1135 | 2.61 | 55% |
| E6 | 1628 | -0.1336 | -6.43 | 44% |
| A6 | 1697 | -0.2396 | -9.18 | 42% |
| B6 | 1636 | -0.2302 | -9.34 | 42% |
| J1 | 1717 | -0.1030 | -4.29 | 45% |
| E1 | 1737 | -0.1622 | -7.10 | 45% |

## 30 minute bars

| window | set | instruments | trades | per instr/yr | net avgR | gross avgR | boot t | win% | overnight | median cost (R) |
|---|---|---|---|---|---|---|---|---|---|---|
| short | explore | 13 | 21489 | 184 | -0.0854 | +0.0002 | -9.35 | 38% | 41% | 0.032 |
| medium | explore | 13 | 17897 | 153 | -0.0653 | +0.0153 | -6.07 | 41% | 38% | 0.029 |
| long | explore | 13 | 9535 | 81 | -0.0520 | +0.0166 | -4.04 | 44% | 36% | 0.024 |
| short | holdout | 13 | 23803 | 189 | -0.1186 | -0.0149 | -14.54 | 38% | 41% | 0.036 |
| medium | holdout | 13 | 20247 | 161 | -0.0855 | +0.0097 | -9.14 | 41% | 39% | 0.033 |
| long | holdout (THE TEST) | 13 | 10945 | 87 | -0.0499 | +0.0324 | -4.52 | 45% | 38% | 0.027 |

**30m, long window: holdout net avgR -0.0499, t -4.52 -> no**

| instrument | trades | net avgR | boot t | win% |
|---|---|---|---|---|
| ES | 820 | -0.0665 | -1.95 | 41% |
| NQ | 724 | +0.0839 | 2.20 | 49% |
| RTY | 756 | +0.0048 | 0.14 | 47% |
| GC | 954 | +0.0453 | 1.29 | 46% |
| SI | 697 | -0.0548 | -1.38 | 42% |
| HG | 749 | +0.0923 | 2.24 | 49% |
| CL | 470 | -0.0870 | -1.90 | 43% |
| NG | 203 | +0.0733 | 1.15 | 53% |
| E6 | 1115 | -0.0927 | -3.65 | 43% |
| A6 | 1103 | -0.2067 | -6.18 | 41% |
| B6 | 1075 | -0.1106 | -3.20 | 46% |
| J1 | 1129 | -0.0545 | -1.96 | 44% |
| E1 | 1150 | -0.0800 | -3.11 | 46% |
