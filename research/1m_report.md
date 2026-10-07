# 1 minute study on the v2 trade set

6192 v2 trades across 41 instruments with 1 minute data. Minute alignment (first minute open equals hourly open): 6191/6192.

## A. Fill realism for resting stop orders (calibration)

Trades whose entry hour's minutes breach the order level: 6192 of 6192 (100%); first minute already past the level (gap fill): 229.

| fill assumption | avgR (all periods) | avgR 2017 to 2026 | median slippage vs line (ticks) | mean slippage (ticks) |
|---|---|---|---|---|
| line | +0.0607 | +0.0481 | +0.0 | -1.0 |
| mid | +0.0279 | +0.0186 | -1.4 | -7.7 |
| worst | +0.0029 | -0.0040 | -2.7 | -14.4 |
| engine (backtest) | +0.0920 | +0.0827 | 0 (minus 2 ticks per round trip in all rows) | |

Read: `mid` is the honest expectation for a stop order; `worst` is a floor. The difference between `line` and `mid` is the slippage the backtest's 2 tick assumption has to cover.

## B. 1 minute confirmation entry (one preregistered test)

- exploration 2008 to 2016: 2581 of 2840 confirmed on 1 minute, avgR +0.0689 vs base +0.1031; median delay 18 min; Sharpe 1.39 -> 0.90, diff -0.50, t -3.89 **(exploration)**
- holdout 2017 to 2026: 3094 of 3352 confirmed on 1 minute, avgR +0.0412 vs base +0.0827; median delay 18 min; Sharpe 1.11 -> 0.58, diff -0.53, t -3.81 **no**
