# Trendline-walk backtest (corrected build)

Mechanized structural trendline-walk strategy on 1H futures bars, with an honest
fill model, causal pivot confirmation, a 131-symbol scan notebook, and a higher
timeframe resampler.

**Defaults are the honest settings.** `run()` now defaults to
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
and fills at the line or the gap open, adding those trades back. This roughly
triples the trade count.

**2. Refit lookahead (`causal`).**
In `refit()` with `causal=False`, the line fit and the touch count could use
pivots up to `K` bars past the decision bar. A pivot at bar `p` is only
confirmable at `p+K`, so those pivots needed bars that had not printed yet. None
of the old runs used `causal=True`, so the prior scan, the training data, and the
monkey control all inherited this peek.

## What the correction cost

Five metals, full 18.5y hourly history (2008 to 2026), `MAXSPAN=1200`, no
slippage. Same data, same exit engine, same parameters. The only difference is
the two fixes above.

| | old (`open`, `causal=False`) | honest (`intrabar`, `causal=True`) |
|---|---|---|
| trades | 1,468 | 3,798 |
| total R | +435.3 | +404.0 |
| mean PF | 1.95 | 1.28 |
| net positive | 5 / 5 | 4 / 5 |

Per symbol profit factor:

| symbol | old | honest @1200 | honest @ unbounded span |
|---|---|---|---|
| PA | 1.98 | 1.51 | 1.60 |
| PL | 2.03 | 1.36 | 1.40 |
| HG | 2.26 | 1.34 | 1.32 |
| GC | 1.85 | 1.21 | 1.25 |
| SI | 1.63 | 0.98 | 1.01 |

Silver does not survive the correction. At the validated span it goes from
+55.7R to -5.5R. That is the single clearest illustration of what the two biases
were worth.

Note that the two fixes were flipped together, so this table does not attribute
the damage between them. Running `fill='intrabar', causal=False` would isolate
the fill effect; that has not been done yet.

### On the span parameter

Relaxing `MAXSPAN` from 1200 to unbounded improves the honest numbers (5,376
trades, +624.7R, mean PF 1.32, 5/5 net positive). Both are reported here on
purpose. Span is a free parameter, and adopting whichever value scores best is
how curve fitting starts. 1200 was the value validated before these results were
known, so it remains the reference.

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
- Results above carry no slippage. `--slip` / `SLIP_TICKS` applies it to symbols
  with a known tick size; at PF 1.2 to 1.3 the margin is thin enough that costs
  matter.

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
   the symbol is parsed from the filename.
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
# honest mode is the default now
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
