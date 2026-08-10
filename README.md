# Trendline-walk backtest (corrected build)

Mechanized structural trendline-walk strategy on 1H futures bars, with an honest
fill model, causal pivot confirmation, a 131-symbol scan notebook, and a higher
timeframe resampler.

**Defaults are the honest settings.** `run()` defaults to
`causal=True, fill='intrabar'`. The pre-correction behaviour is still available
explicitly (`--legacy` on the CLI, or `causal=False, fill='open'`) and prints a
warning when used.

## What changed in this build (read this first)

Two correctness problems were found in the detector. Both inflated results in the
exact mode every tool was using. Every number below is net of both fixes.

**1. Entry fill: the trigger, not just the price.**
The original entry counted a trade only when price broke THROUGH the line by
`tol` (0.15%), then filled at the line. A live resting order fills the moment
price TOUCHES the line, and those marginal touches are mostly scratches and
losses that the old test silently dropped. `fill='intrabar'` triggers on touch
and fills at the line or the gap open, adding those trades back. This more than
quadruples the trade count.

**2. Refit lookahead (`causal`).**
In `refit()` with `causal=False`, the line fit and the touch count could use
pivots up to `K` bars past the decision bar. A pivot at bar `p` is only
confirmable at `p+K`, so those pivots needed bars that had not printed yet. None
of the old runs used `causal=True`, so the prior scan, the training data, and the
monkey control all inherited this peek.

## What the correction cost

Full scan, **all 131 instruments**, 18.5y of hourly data (2008 to 2026),
`MAXSPAN=1200`, no slippage. Same data, same exit engine, same parameters. The
only difference is the two fixes above.

| | old (`open`, `causal=False`) | honest (`intrabar`, `causal=True`) |
|---|---|---|
| trades | 16,759 | 70,347 |
| total R | +5,224.3 | +4,313.6 |
| mean PF | 2.50 | 1.19 |
| median PF | 1.93 | 1.16 |
| net positive | 117 / 131 | 106 / 131 |

**106 net-positive instruments overstates what is really there.** The
distribution is thin at the top:

| threshold | instruments clearing it |
|---|---|
| PF > 1.0 | 106 / 131 |
| PF > 1.1 | 84 / 131 |
| PF > 1.2 | 54 / 131 |
| PF > 1.3 | 36 / 131 |
| PF > 1.5 | 13 / 131 |

A large share of the 106 sit near 1.05 and will not survive transaction costs.
Treat the PF > 1.3 count as the realistic universe.

### Reference instruments (honest, span 1200)

| symbol | trades | win % | total R | avg R | PF |
|---|---|---|---|---|---|
| PA | 621 | 45.2 | +121.6 | +0.20 | 1.51 |
| PL | 768 | 44.9 | +104.3 | +0.14 | 1.36 |
| HG | 775 | 44.8 | +102.0 | +0.13 | 1.34 |
| CL | 448 | 41.7 | +43.9 | +0.10 | 1.24 |
| GC | 974 | 43.0 | +81.6 | +0.08 | 1.21 |
| SI | 660 | 39.8 | -5.5 | -0.01 | 0.98 |
| NQ | 844 | 42.4 | -9.7 | -0.01 | 0.97 |
| ES | 972 | 39.3 | -24.0 | -0.02 | 0.95 |

Metals and crude carry the result. **Silver does not survive the correction** —
it went from PF 1.63 to 0.98. Neither do the equity indices, which is the
expected outcome: their old-mode profits came from long-biased entries in a bull
market rather than from edge, which is exactly what the randomized-entry control
exists to detect.

Note that the two fixes were flipped together, so this does not attribute the
damage between them. Running `fill='intrabar', causal=False` would isolate the
fill effect; that has not been done yet.

### On the span parameter

Relaxing `MAXSPAN` from 1200 to unbounded gives 107,867 trades, +5,377.7R, mean
PF 1.18, 108/131 net positive — more trades and more total R at effectively the
same profit factor. Both are reported on purpose. Span is a free parameter, and
adopting whichever value scores best is how curve fitting starts. 1200 was the
value validated before these results were known, so it remains the reference.

## Other findings

- **The break does not predict direction.** A matched null with random direction
  on the real signal bars did about as well as the real direction. The edge such
  as it is comes from entering at a structural level with a tight stop, plus the
  exit engine — not from the trendline calling long versus short. This falsifies
  the original thesis.
- **4h is weaker than 1h** on the metals (GC 1h PF 1.21 vs 4h 1.15). Higher
  timeframe did not rescue it.
- The earlier model-integrity audit was run on a simpler detector that lacks
  `refit()` and `causal`, so its conclusions do not fully describe this code.

## Known limitations

- **No frozen out-of-sample holdout.** Every window was visible during
  development, so the per-period testing is robustness evidence, not a clean
  holdout.
- **No capacity analysis.** The size at which slippage erodes the edge is
  untested.
- **Never run live.** There is a working IBKR bracket-order execution path,
  validated end to end against the exit engine, but no live or forward paper
  track record exists. Any forward performance claim would be unsupported.
- **The results above carry no slippage.** At a median PF of 1.16 the margin is
  thin enough that costs matter materially. `--slip` / `SLIP_TICKS` applies
  slippage to symbols with a known tick size; a costed rerun is the next step.

## Setup

```bash
pip3 install -r requirements.txt    # numpy, pandas, matplotlib
```

Python 3.9+.

## The scan notebook (main tool)

`scan_trendline.ipynb` runs every symbol at honest settings across a sweep of
MAXSPAN values, prints per-symbol metrics, an old-vs-honest comparison, and a
survivor count.

1. Put `backtest_hull.py` and the notebook in the same folder.
2. Set `DATA_DIR` to your data folder. FirstRateData `.txt` files work as-is;
   the symbol is parsed from the filename. If the files live in cloud storage,
   make sure they are downloaded locally first — otherwise symbols fail with
   `TimeoutError` and silently drop out of the scan.
3. Start with the preset `SYMBOLS = ["GC","PL","HG","PA","SI"]`. The sanity-check
   cell asserts GC comes back at PF 1.21 / +81.6R at span 1200. If it does not,
   the config is wrong — fix it before reading anything else.
4. Set `SYMBOLS = None` for the full run. Roughly 3 to 4 hours for 131 symbols.

Outputs land in `results/` with a datestamp.

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
python3 run_backtest.py DATA_DIR/GC_*.txt DATA_DIR/PL_*.txt DATA_DIR/HG_*.txt

# whole folder, with slippage on symbols that have a tick size
python3 batch_backtest.py --slip 1
python3 batch_backtest.py GC PL HG

# reproduce the old inflated numbers explicitly
python3 run_backtest.py DATA_DIR/GC_*.txt --legacy

# random-entry control (honest defaults)
python3 random_entry_control.py DATA_DIR/GC_*.txt DATA_DIR/PL_*.txt --sims 500
```

**On the monkey control:** it randomizes BOTH the entry bar and the direction, so
a high z is not proof the entry signal is the edge. The direction question is
settled by the matched null, which found direction barely matters on the metals.
Read a modest z as expected, not as failure. The older default compared a
lookahead strategy against clean random entries and produced an inflated z.

## Training data for the tier model

```bash
python3 make_training_data.py MGC PL PA SI HG
```

Forced to `causal=True, fill='intrabar'` so the features (touches, span, slope)
are known at entry. The old default leaked the future into the features
themselves, separate from label leakage. Train only on `FEATURE_COLS`; never feed
a `LABEL_COL`.

## CSV format

`time,open,high,low,close[,volume]` — time may be epoch seconds, epoch ms, or a
datetime string. Header optional. Use full-size ratio-adjusted continuous series.

## Files

- `backtest_hull.py` — detector, exit engine, loader, `fill` + `causal` params.
- `scan_trendline.ipynb` — 131-symbol scan with MAXSPAN sweep and timeframe knob.
- `resample_tf.py` — 1h to 4h (or any rule) resampler.
- `run_backtest.py` / `batch_backtest.py` — CLI backtests.
- `random_entry_control.py` — monkey control (honest defaults).
- `make_training_data.py` — tier-model training set (honest defaults).
- `check_orders.py`, `DEPLOY.md`, `docker-compose.yml` — live/paper infra.
- `results/` — datestamped scan output.
