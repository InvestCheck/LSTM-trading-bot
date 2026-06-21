# Trendline-walk backtest

A mechanized version of the structural trendline-walk strategy on 1H bars,
with a random-entry control to test where the edge comes from.

## Setup

```bash
pip install -r requirements.txt   # numpy, matplotlib
```

Python 3.9+.

## Run a backtest

```bash
# one symbol (sample gold file included)
python run_backtest.py data/gold.csv

# several at once -> per-symbol rows plus a portfolio line
python run_backtest.py data/GC.csv data/SI.csv data/HG.csv data/PL.csv data/PA.csv

# pin the start date
python run_backtest.py data/GC.csv --start 2008-03-01 --name Gold
```

Output is per symbol: trades, win %, total R, average R, profit factor, and the
long/short split.

## Random-entry control (the monkey test)

```bash
python random_entry_control.py data/gold.csv --sims 500
python random_entry_control.py data/GC.csv data/SI.csv data/HG.csv --sims 500 --plot monkey.png
```

Same trade counts, same exit engine, same stop sizing, only the entry bar and
direction randomized. Reports the strategy total vs the random distribution and
the z-score. A large positive z with ~0% of random runs beating the strategy
means the edge is in the entry selection, not the exits or market drift.

## CSV format

`time,open,high,low,close[,volume]`

The `time` column auto-detects:
- epoch seconds (old TradingView exports) e.g. `1672700400`
- epoch milliseconds e.g. `1672700400000`
- datetime strings (FirstRateData) e.g. `2008-01-02 09:00:00`, `01/02/2008 09:00`, ISO 8601

A header row is optional and skipped automatically. Rows are sorted ascending,
so newest-first files are fine.

## FirstRateData notes

- The detector is percentage-based and R-based, so the contract multiplier does
  not affect results. The cap is off by default. Use the **full-size**
  continuous series (GC, SI, HG, PL, PA, NQ, ES, CL), not the micros, because
  the full-size symbols go back to 2008 while the micros start 2010 to 2021.
- Use the **ratio-adjusted** continuous series, since the detector measures
  moves in percent and ratio adjustment preserves percentage gaps across rolls.
- Keep the parameters frozen across symbols. If a symbol only works after
  retuning, that is curve fitting, not an edge.

## What is known so far

- Validated on metals (gold, platinum) and holds out of sample on palladium,
  silver, copper. Copper is the standout.
- Crude oil fails outright. Energy is the wrong character for this strategy.
- For trending instruments like equity indices (NQ, ES), read the random-entry
  z-score, not the raw return. A long-biased entry makes money in a bull market
  by accident; the monkey control separates skill from drift.

## Files

- `backtest_hull.py` — detector, exit engine, flexible CSV loader, and the
  shared `exit_sim` used by the control.
- `run_backtest.py` — CLI to backtest one or many files.
- `random_entry_control.py` — CLI Monte-Carlo random-entry control.
- `data/gold.csv` — sample 1H gold series so everything runs out of the box.

## Parameters

Defaults live in `run()` in `backtest_hull.py`: trendline tolerance, touch band,
break tolerance, minimum 7-day span, minimum 3 touches separated by a bar gap,
and the exit engine (200 EMA wick ratchet gated at 0.5R, breakeven at +1R,
21 EMA close trail, parabolic exit at 3.5x ATR from the 21 EMA).
