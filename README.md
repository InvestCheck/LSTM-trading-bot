# Trendline-walk backtest (corrected build)

Mechanized structural trendline-walk strategy on 1H futures bars, with an honest
fill model, causal pivot confirmation, per-instrument transaction costs, a
131-symbol scan notebook, and a higher timeframe resampler.

**Headline result: after realistic costs, the strategy does not work.** Across
131 instruments and 18.5 years of hourly data it loses money in aggregate. Four
instruments survive at conventional significance. Details below.

**Defaults are the honest settings.** `run()` defaults to
`causal=True, fill='intrabar'`. The pre-correction behaviour is available
explicitly (`--legacy`, or `causal=False, fill='open'`) and prints a warning.

## What changed in this build (read this first)

Three problems were found, each of which inflated results in the exact mode
every tool was using.

**1. Entry fill: the trigger, not just the price.**
The original entry counted a trade only when price broke THROUGH the line by
`tol` (0.15%), then filled at the line. A live resting order fills the moment
price TOUCHES the line, and those marginal touches are mostly scratches and
losses that the old test silently dropped. `fill='intrabar'` triggers on touch
and fills at the line or the gap open. This more than quadruples the trade count.

**2. Refit lookahead (`causal`).**
In `refit()` with `causal=False`, the line fit and touch count could use pivots
up to `K` bars past the decision bar. A pivot at bar `p` is only confirmable at
`p+K`, so those pivots needed bars that had not printed yet. No prior run used
`causal=True`, so the earlier scan, the training data, and the monkey control all
inherited this peek.

**3. Missing tick sizes meant no transaction costs.**
`run()` applies zero slippage when `tick` is unset. The tick table originally
covered 13 instruments, so 118 of 131 silently reported pre-cost results while
appearing to be a costed run. `instruments.py` now carries a verified tick size
per instrument, and the scan prints any symbol that would still be uncosted.

All three shared a failure mode worth naming: **the permissive default was also
the flattering one.** Each produced better numbers rather than an error.

## Results

Full scan, all 131 instruments, 18.5y hourly (2008 to 2026), `MAXSPAN=1200`,
1 tick round-trip slippage applied per instrument.

| | old (`open`, `causal=False`) | honest (`intrabar`, `causal=True`) |
|---|---|---|
| trades | 16,759 | 70,347 |
| total R | +4,432.0 | **-3,062.1** |
| mean PF | 2.19 | 1.03 |
| median PF | — | 1.02 |
| net positive | — | 72 / 131 |

The corrected, costed portfolio is **net negative**. The apparent edge in the
original build came from the two look-ahead biases and from not paying for
execution.

### Survivors, and how many are noise

72 instruments are net positive, but with 131 tests some will clear any
threshold by chance. The t-statistic on mean R per instrument separates them:

| threshold | instruments | of those, t > 2 | of those, t > 3 |
|---|---|---|---|
| PF > 1.0 | 72 | 12 | 4 |
| PF > 1.1 | 47 | 12 | 4 |
| PF > 1.2 | 30 | 11 | 4 |
| PF > 1.3 | 19 | 8 | 4 |
| PF > 1.5 | 8 | 4 | 2 |

With 131 simultaneous tests, t > 2 is the wrong bar — roughly 6 instruments would
be expected to clear it by chance alone, which is half of the 12 observed. **t > 3
is the defensible threshold**, and four instruments clear it:

| symbol | instrument | trades | PF | avg R | total R | t |
|---|---|---|---|---|---|---|
| J7 | E-mini Japanese Yen | 1,460 | 1.65 | +0.23 | +342.4 | 5.87 |
| J1 | Japanese Yen | 1,383 | 1.43 | +0.16 | +224.3 | 4.25 |
| PA | Palladium | 621 | 1.47 | +0.19 | +115.3 | 3.78 |
| ZR | Rough Rice | 318 | 1.66 | +0.24 | +75.0 | 3.48 |

**J7 and J1 are the same underlying**, so this is three independent bets, not
four. That is a thin result from a 131-instrument search, and it should be
treated as a hypothesis to test out of sample rather than as a finding.

Instruments with a high profit factor and very few trades — FDIV at PF 1.83 on 11
trades, PRK at 1.73 on 10, KRW at 2.70 on 65 — are reported in the tables but are
underpowered. None reaches t > 2.

### What costs did to the previous headline

| | no slippage | 1 tick round trip |
|---|---|---|
| mean PF | 1.19 | 1.03 |
| total R | +4,313.6 | -3,062.1 |
| net positive | 106 / 131 | 72 / 131 |
| PF > 1.3 | 36 | 19 |

Per instrument:

| symbol | PF pre-cost | PF costed | t |
|---|---|---|---|
| PA | 1.51 | 1.47 | 3.78 |
| PL | 1.36 | 1.30 | 2.92 |
| HG | 1.34 | 1.24 | 2.34 |
| CL | 1.24 | 1.17 | 1.29 |
| GC | 1.21 | 1.16 | 1.87 |
| SI | 0.98 | 0.89 | -1.20 |
| NQ | 0.97 | 0.94 | -0.79 |
| ES | 0.95 | 0.85 | -2.02 |

The metals story does not hold up. Palladium survives; platinum is marginal;
gold, copper, and crude are no longer distinguishable from zero. Silver and the
equity indices are negative. The equity index result is the expected one — their
old-mode profits came from long-biased entries in a bull market rather than from
edge, which is exactly what the randomized-entry control exists to detect.

### On the span parameter

Unbounded `MAXSPAN` is worse once costs apply: 107,867 trades, -8,860.1R, mean PF
1.02. More trades simply means more slippage paid. `MAXSPAN=1200` remains the
reference, as it was the value validated before any of these results were known.

## Other findings

- **The break does not predict direction.** A matched null with random direction
  on the real signal bars did about as well as the real direction. Whatever edge
  exists comes from entering at a structural level with a tight stop plus the
  exit engine, not from the trendline calling long versus short. This falsifies
  the original thesis.
- **4h is weaker than 1h** on the metals. Higher timeframe did not rescue it.
- The earlier model-integrity audit ran on a simpler detector lacking `refit()`
  and `causal`, so its conclusions do not fully describe this code.

## Known limitations

- **No frozen out-of-sample holdout.** Every window was visible during
  development, so per-period testing is robustness evidence, not a clean holdout.
  The four surviving instruments in particular need one before they mean
  anything.
- **No capacity analysis.** The size at which market impact erodes the edge is
  untested.
- **Never run live.** There is a working IBKR bracket-order execution path,
  validated end to end against the exit engine, but no live or forward paper
  track record exists. Any forward performance claim would be unsupported.
- **Slippage is a flat 1 tick round trip.** Real slippage varies with volatility,
  session, and order size, and is worse in the thin contracts where several of
  the apparent survivors trade.
- **The two detector fixes were applied together**, so this does not attribute
  the damage between them. Running `fill='intrabar', causal=False` would isolate
  the fill effect; not yet done.

## Setup

```bash
pip3 install -r requirements.txt    # numpy, pandas, matplotlib
```

Python 3.9+.

## The scan notebook (main tool)

`scan_trendline.ipynb` runs every symbol at honest settings across a MAXSPAN
sweep and prints per-symbol metrics, an old-vs-honest comparison, significance
counts, and a survivor count.

1. Put `backtest_hull.py` and `instruments.py` in the same folder as the notebook.
2. Set `DATA_DIR`. FirstRateData `.txt` files work as-is; the symbol is parsed
   from the filename. If the files live in cloud storage, download them locally
   first — otherwise symbols fail with `TimeoutError` and silently drop out.
3. Check the two startup lines: how many tick sizes are verified, and which
   symbols would report pre-cost results. Do not read costed conclusions off a
   run with symbols on that second list.
4. The sanity-check cell asserts GC returns PF 1.16 / +64.3R at span 1200 with
   `SLIP_TICKS=1`. If it does not, fix the config before reading anything else.
5. `SYMBOLS = None` for the full run. Roughly 3 to 4 hours for 131 symbols.

Outputs land in `results/` with a datestamp.

## Instrument metadata

`instruments.py` maps every symbol to its full name and tick size.

FirstRateData reuses tickers that mean something else on other venues, so do not
fill tick sizes from memory. `AD` is the Canadian Dollar here (Australian Dollar
is `A6`); `C` is London Cocoa (Corn is `ZC`); `B` is Brent. `TICKS` is built only
from verified entries, and `UNVERIFIED` lists the rest.

## Higher timeframe (4h)

```bash
python3 resample_tf.py seed seed_4h --rule 4h
```

Then set `DATA_DIR="seed_4h"` and `BAR_HOURS=4`. Span and gap parameters
auto-scale. The exit-engine periods (14/21/200) are NOT rescaled; a full 4h
retune would change them, but a win that only appears after per-timeframe
retuning is curve fitting.

## CLI tools

```bash
# honest mode is the default
python3 run_backtest.py DATA_DIR/GC_full_1hour_continuous_ratio_adjusted.txt

# whole folder, with slippage
python3 batch_backtest.py --slip 1

# reproduce the old inflated numbers explicitly
python3 run_backtest.py DATA_DIR/GC_*.txt --legacy

# random-entry control (honest defaults)
python3 random_entry_control.py DATA_DIR/GC_*.txt DATA_DIR/PL_*.txt --sims 500
```

**On the monkey control:** it randomizes BOTH entry bar and direction, so a high
z is not proof the entry signal is the edge. The direction question is settled by
the matched null, which found direction barely matters. Read a modest z as
expected. The older default compared a lookahead strategy against clean random
entries and produced an inflated z.

## Training data for the tier model

```bash
python3 make_training_data.py MGC PL PA SI HG
```

Forced to `causal=True, fill='intrabar'` so the features (touches, span, slope)
are known at entry. The old default leaked the future into the features
themselves, separate from label leakage. Train only on `FEATURE_COLS`; never feed
a `LABEL_COL`.

Given the costed results above, a tier model trained on this signal is fitting a
strategy with no aggregate edge. Treat it as an exercise unless the four
surviving instruments hold up out of sample.

## CSV format

`time,open,high,low,close[,volume]` — time may be epoch seconds, epoch ms, or a
datetime string. Header optional. Use full-size ratio-adjusted continuous series.

## Files

- `backtest_hull.py` — detector, exit engine, loader, `fill` + `causal` params.
- `instruments.py` — symbol to name and tick size mapping.
- `scan_trendline.ipynb` — 131-symbol scan, MAXSPAN sweep, significance counts.
- `resample_tf.py` — 1h to 4h (or any rule) resampler.
- `run_backtest.py` / `batch_backtest.py` — CLI backtests.
- `random_entry_control.py` — monkey control (honest defaults).
- `make_training_data.py` — tier-model training set (honest defaults).
- `check_orders.py`, `DEPLOY.md`, `docker-compose.yml` — live/paper infra.
- `results/` — datestamped scan output.
