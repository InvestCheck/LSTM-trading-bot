# v3 studies: tier model with ADX and breadth, vol targeting, chandelier in the stop rule subset

7821 exploration trades (2008 to 2016), 9622 holdout trades. Three preregistered tests, one sided z 1.64. This is one more look at the holdout; count it.

v2 gate reproduced here: 2944 exploration and 3478 holdout trades, holdout avgR +0.0776.

## A. Tier model refit with ADX, breadth, cluster breadth

| split of the v2 holdout trades | kept n, avgR | rest n, avgR | diff | boot t | verdict |
|---|---|---|---|---|---|
| **new score >= exploration v2 median (the test)** | 1862, +0.1236 | 1616, +0.0247 | +0.0989 | 2.56 | **PASS** |
| old score >= exploration v2 median (reference) | 1836, +0.1125 | 1642, +0.0386 | +0.0739 | 1.86 | reference |
| ADX <= 20 (reference) | 1067, +0.1577 | 2411, +0.0422 | +0.1155 | 2.95 | reference |

New model weights (per std, exploration fit): p_d_e200 -0.056, p_d_e50 +0.052, inst_cost -0.043, p_d_e21 -0.039, p_room +0.037, FX +0.033, hour_cos -0.026, sunday -0.025, EQ -0.022, p_mom5 -0.021

## B. Vol targeting

| set | book | Sharpe | max DD (R units) | total R | leverage min/median/max |
|---|---|---|---|---|---|
| explore | flat, one unit per trade | 1.31 | 56.1 | +287 | 1 / 1 / 1 |
| explore | vol target, 20 day lookback | 1.28 | 49.1 | +315 | 0.39 / 0.97 / 3.64 |
| explore | vol target, 60 day lookback | 1.34 | 47.1 | +313 | 0.62 / 0.98 / 2.67 |
| explore | vol target, 120 day lookback | 1.39 | 50.5 | +313 | 0.69 / 0.97 / 2.67 |
| holdout | flat, one unit per trade | 1.05 | 43.2 | +270 | 1 / 1 / 1 |
| holdout | vol target, 20 day lookback | 1.16 | 40.6 | +348 | 0.46 / 0.95 / 3.43 |
| holdout | vol target, 60 day lookback | 1.06 | 40.0 | +281 | 0.62 / 0.95 / 2.61 |
| holdout | vol target, 120 day lookback | 1.06 | 35.1 | +265 | 0.70 / 0.95 / 1.27 |

Best lookback on exploration: **120 days**. Holdout Sharpe difference vs flat: **+0.02, boot t 0.50 -> no**. Leverage is relative to one unit of risk per trade; a median near 1 means the target matched the exploration vol.

## C. Chandelier 3 ATR exit, v2 holdout trades

| subset | n | engine avgR | chandelier avgR | paired diff | boot t | verdict |
|---|---|---|---|---|---|---|
| **stop <= 2.5 ATR (the test)** | 1028 | +0.1489 | +0.2221 | +0.0732 | 1.59 | **no** |
| all v2 (reference) | 2934 | +0.0888 | +0.1306 | +0.0419 | 1.66 | reference |
