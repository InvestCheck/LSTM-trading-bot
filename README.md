# Trendline-walk backtest (corrected build)

Mechanized structural trendline-walk strategy on 1H futures bars, with a causal
detector, an honest fill model, per-instrument transaction costs, a 131-symbol
scan, pre-registered holdout protocols, and dependence-aware statistics.

**Headline result, in two parts.**

**No individual instrument shows an edge that survives correction for the size
of the search.** A selection run on pre-2020 data only, at a Bonferroni
threshold for 131 tests, returns an empty set. The four instruments an earlier
build reported as survivors do not hold: two were an arithmetic defect, and two
do not clear the threshold on data available before the holdout.

**The pooled signal is nonetheless real, and roughly half the size of its own
execution cost.** A random-entry control on instruments chosen without reference
to performance gives z = 2.7. Gross of costs, the median t across 92 instruments
is +1.31. On the executable subset the strategy is net positive at one tick
round-trip slippage, but breakeven for the whole book sits at 1.03 ticks and
commissions are not yet modelled.

Those are different questions, and this project spent most of its life
conflating them. Neither result is out of sample.

**Defaults are the honest settings.** `run()` defaults to
`causal=True, fill='intrabar'`. The pre-correction behaviour is available
explicitly (`--legacy`, or `causal=False, fill='open'`) and prints a warning.

---

## Four sources of optimistic bias, all now corrected

Each inflated results in the exact mode every tool was using, and each shared a
failure mode worth naming: **the permissive default was also the flattering
one.** Every defect produced better numbers rather than an error.

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
per instrument, and `batch_backtest.py` prints any symbol that would still be
uncosted before it runs.

**4. Price rounding on low-priced instruments.** *(found 22 Aug 2026)*
`backtest_hull.py` stored `entry` and `stop` as `round(x, 4)`, and the exit
engine read those rounded values back while computing `R` from the unrounded
ones. On an instrument priced near 0.0068 with a 1e-6 tick, four decimal places
quantises the price grid to 100 ticks. Confirmed by A/B on matched synthetic
series: gold-priced data is bit-identical either way, yen-priced data moves avgR
by 0.05R and changes the trade count.

The two instruments affected were the two the published result rested on:

| | before fix | after fix |
|---|---|---|
| J7 | 1,460 tr, +342.4R, avgR +0.23, PF 1.65 | 1,397 tr, +82.7R, avgR +0.06, PF 1.15 |
| J1 | 1,383 tr, +224.3R, avgR +0.16, PF 1.43 | 1,291 tr, +98.6R, avgR +0.08, PF 1.19 |
| PA | 621 tr, +115.3R, avgR +0.19, PF 1.47 | unchanged |
| ZR | 318 tr, +75.0R, avgR +0.24, PF 1.66 | +76.0R, avgR +0.24, PF 1.67 |

J7's headline was 76% defect. PA and ZR trade at price levels where four decimal
places are invisible, which is why they did not move.

---

## Results

Full scan, all 131 instruments, 18.5y hourly (2008 to 2026), span 168 to 1200
bars, 1 tick round-trip slippage applied per instrument.

| | old (`open`, `causal=False`) | honest (`intrabar`, `causal=True`) |
|---|---|---|
| trades | 16,759 | 70,187 |
| total R | +4,432.0 | **−3,564.2** |
| mean PF | 2.19 | ~1.03 |

The apparent edge in the original build came from the two lookahead biases and
from not paying for execution. The corrected figure moved from −3,062.1R to
−3,564.2R when the rounding defect was fixed.

That aggregate figure is misleading in a specific way, addressed below.

### No instrument survives a clean selection

Stage 1 (`holdout_protocol.md`) split each survivor's trades at 2020-01-01 and
scored the second half. That test was contaminated: the survivors were chosen on
*full-sample* t, and the full sample contains the holdout. The share of the
selection statistic that is literally the holdout is `sqrt(n_post / n_full)` —
0.62 for J7, 0.61 for J1. Roughly 60% of the evidence that chose them was the
data used to confirm them.

Stage 2 (`holdout_protocol_stage2.md`, registered before the run) fixes the
ordering: rank on pre-2020 data only, apply a Bonferroni threshold for 131 tests
of t > 3.55, freeze the surviving list to disk, then score post-2020 once.

Ranking on 2020-01-01, instruments with n ≥ 100:

```
PA   445 tr  PF 1.52  avgR +0.199  t 3.47
ZR   255 tr  PF 1.64  avgR +0.231  t 3.12
PL   556 tr  PF 1.37  avgR +0.144  t 2.95
MGC  528 tr  PF 1.32  avgR +0.131  t 2.49
...
J7   876 tr  PF 1.14  avgR +0.053  t 1.53   (17th)
```

Nothing clears 3.55. `results/selection_pre2020-01-01.json` records an empty
selection. Per the registered protocol that is a complete result, and there was
nothing to score. **All stage 1 holdout results are withdrawn** — they were
computed on the defective data, and the JPY instruments they turned on are
exactly the ones the defect touched.

Two follow-ups confirm this rather than rescue it.

**Serial dependence is not the problem.** A stationary block bootstrap
resampling whole calendar blocks from the demeaned trade series gives an
inflation factor of 1.00 for PA and 0.83 for ZR across month, quarter and year
blocks. The individual t-statistics are correctly calibrated. This was a stated
hypothesis of the project and it is rejected.

**The leaders are not leaders.** Across the 78 clean instruments the
cross-sectional spread of t is 1.43, wider than the 1.0 expected under pure
noise. Since the individual statistics are calibrated, that excess is genuine
heterogeneity in edge, implying a true-effect sd of 1.02 and an empirical Bayes
shrinkage factor of 0.51 toward the median of +0.37:

| | naive t | posterior |
|---|---|---|
| PA | +3.47 | **+1.95** |
| ZR | +3.12 | +1.77 |
| PL | +2.95 | +1.68 |

Maximum posterior across all 78 is +1.95. Reading the largest of 78 draws as
evidence is the error being corrected.

### The cost model dominates a subset of contracts

Of 92 eligible instruments, 14 have a median stop narrow enough that one tick
round trip exceeds 10% of the bet. On ZQ the median stop is **1.5 ticks wide**,
so cost is 135% of R and every trade opens down 1.35R before the market moves.
These are not strategy results:

```
ZQ 1.5 ticks (135% of R)   ER 2.7 (75%)   SR3 3.1 (65%)   SR1 3.6 (55%)
also excluded: EBM FGBM FGBS JB L MP PJY RM T6 US ZN ZO
```

That block has a median t of −2.57 and accounts for essentially the entire
portfolio deficit. The exclusion criterion is mechanical rather than performance
based: **a stop narrower than the round-trip cost cannot be executed as
designed.** `tick_sanity.py` reports it per instrument and prints the full
sensitivity column at every cutoff, so the threshold cannot be chosen to flatter
the total.

Slippage sensitivity over the whole book, 70,187 trades:

| slip (per side) | total R |
|---|---|
| 0 | +3,798.3 |
| 0.5 | +116.8 |
| 1 | −3,564.2 |
| 2 | −10,926.8 |

Breakeven is at 1.03 ticks round trip, **with no commissions modelled.** That is
what you pay on a one-tick-wide market filled exactly at the touch, so the whole
book is at best marginal and commissions push it under. On the micro contracts
(MGC, MES, MNQ, M2K, MBT) a $4 round-trip commission can exceed 5% of the bet on
its own, which is larger than the entire measured edge.

### The signal is real, and small

The entry is not noise. `random_entry_control.py` matches trade count, stop size
and exit engine, randomising only entry bar and direction:

- On 12 instruments drawn by fixed seed from the clean subset, chosen without
  reference to performance: strategy +240.3R against a random mean of −17.3R
  (sd 95.8), with 0.4% of 500 random runs beating it, **z = 2.7**.
- An earlier run on the four gross leaders gave z = 6.3. **That number is
  inflated and should not be quoted.** The instruments had been selected on
  performance, so a selected maximum was being compared against an unbiased
  random arm.

Gross of costs, the pre-2020 median t across 92 instruments is **+1.31**, against
+0.37 costed. A median is not a selected maximum, so it is not subject to the
multiplicity problem that killed PA. The signal has broad predictive content and
is roughly half the size of what it costs to harvest.

### Longer trendlines give better signals, not bigger ones

Span configs on the executable subset. One zero-slippage pass per config with
costs derived analytically, which is exact because the engine charges
`2 * slip * tick / R` and `R_px` in the trade file is that same R
(`span_sweep.py`):

| span (bars) | trades | gross avgR | med ticks | cost/bet | net @1 tick |
|---|---|---|---|---|---|
| 168..1200 (reference) | 57,452 | +0.0635 | 63.0 | 3.2% | +757.1 |
| 720..4320 | 30,802 | +0.0701 | 62.8 | 3.2% | +560.5 |
| 2160..17520 | 19,426 | **+0.0779** | 64.2 | 3.1% | +513.3 |
| 168..unbounded | 88,022 | +0.0673 | 64.3 | 3.1% | +1,511.8 |

Median stop distance is flat at 63 to 64 ticks across every config. The
hypothesis was that longer lines sit further from price and give bigger bets,
lowering the cost fraction. **That mechanism does not exist.** R is set by the
ATR stop, not by how long the line took to form.

Gross avgR nonetheless rises monotonically with the span floor. Longer structure
produces better signals rather than larger ones, which supports the top-down
thesis by a different route than the one proposed.

**The previous claim that unbounded span is worse is withdrawn.** It read
−8,860R on 107,867 trades. On the corrected build with unexecutable instruments
excluded it is +1,512R net at one tick. Both the rounding defect and the
ZQ-class contracts were driving that conclusion.

---

## What is and is not supported

Supported:

- The entry signal carries real information (z = 2.7 on an unselected sample).
- Serial dependence between trades is not inflating these statistics.
- Longer span floors improve per-trade edge monotonically.
- The pooled signal on the executable subset is positive net of one tick
  round-trip slippage.
- The reported portfolio loss is driven by contracts where execution cost
  exceeds the bet size, not by the signal.

Not supported:

- **Any claim about a specific instrument.** Nothing clears a
  multiplicity-corrected threshold, and PA at 3.47 against 3.55 is a miss that
  cannot be promoted by re-reading data it has already been measured on.
- **Any claim about JPY.** That result was a rounding artifact.
- **Any claim about a metals cluster.** PA, PL, MGC, HG and GC ranking near the
  top is what correlated instruments do under the null.
- **Any claim of out-of-sample validity.** Every number above is full-sample on
  data used repeatedly for selection. The span result is explicitly exploratory.

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

- **No frozen out-of-sample holdout, and none remains available.** The universe
  has been used for instrument selection, contamination analysis, the span
  sweep, and four rounds of defect hunting. The 2020-01-01 split in particular
  has been examined repeatedly. Forward data is the only data this project has
  not already spent. See `forward_test_protocol.md`.
- **Commissions are not modelled anywhere.** At 3.1% slippage against a 7.8%
  gross edge, commission is not a rounding error.
- **No capacity analysis.** The size at which market impact erodes the edge is
  untested, as is the practicality of holding positions in ~90 contracts at once.
- **Never run live.** There is a working IBKR bracket-order execution path,
  validated end to end against the exit engine, but no live or forward paper
  track record exists. Any forward performance claim would be unsupported.
- **Slippage is a flat 1 tick round trip.** Real slippage varies with volatility,
  session, and order size. Breakout entries are stop orders that routinely fill
  through the touch, so the flat assumption is optimistic in fast markets.
- **Limit and stop-limit entries do not fix this.** A passive limit at the line
  fills only when price comes back, which selects the failures; a stop-limit
  caps the price paid but misses the fastest breakouts. Both convert an explicit
  cost into an invisible one, which is the same class of error as defect 2
  above. Any future model of limit entries must model the non-fills.
- **The two detector fixes were applied together**, so this does not attribute
  the damage between them. Running `fill='intrabar', causal=False` would isolate
  the fill effect; not yet done.

---

## Setup

```bash
pip3 install -r requirements.txt    # numpy, pandas, matplotlib
```

Python 3.9+.

## CLI tools

```bash
# honest mode is the default
python3 run_backtest.py DATA_DIR/GC_full_1hour_continuous_ratio_adjusted.txt

# whole folder, with slippage. --data-dir reads the FirstRateData .txt files
# directly, resolving symbols the same way the scan notebook does.
python3 batch_backtest.py --data-dir DATA_DIR --slip 1

# span window. MINSPAN/MAXSPAN bound how long a line must have been forming
# before a break counts. Defaults 168/1200 = 7 to 50 days on 1h bars.
python3 batch_backtest.py --data-dir DATA_DIR --minspan 2160 --maxspan 17520

# reproduce the old inflated numbers explicitly
python3 run_backtest.py DATA_DIR/GC_*.txt --legacy

# random-entry control (honest defaults)
python3 random_entry_control.py DATA_DIR/GC_*.txt DATA_DIR/PL_*.txt --sims 500
```

**On the monkey control:** it randomizes BOTH entry bar and direction, so a high
z is not proof the entry signal is the edge. The direction question is settled by
the matched null, which found direction barely matters. Read a modest z as
expected. Never select the instruments by performance first — that inflates z by
comparing a selected maximum against an unbiased random arm.

## Cost and execution diagnostics

```bash
# median stop distance in ticks per instrument, worst first
python3 tick_sanity.py

# portfolio total at every exclusion cutoff, so the threshold cannot be
# chosen to flatter the headline
python3 tick_sanity.py --portfolio

# span sweep: gross edge and cost per bet, one pass per config
python3 span_sweep.py --data-dir DATA_DIR
python3 span_sweep.py --data-dir DATA_DIR --split-at 2020-01-01
```

`span_sweep.py` reports gross avgR, median ticks and cost per bet rather than
total R. Total R is the wrong number: a config can lose more in aggregate simply
by taking more trades while each bet gets cheaper to hold.

## Holdout protocols

```bash
# stage 2: select on pre-2020 only, commit the frozen file, then score once
python3 holdout_stage2.py select
git add results/selection_pre2020-01-01.json && git commit && git push
python3 holdout_stage2.py score

# diagnostics, run only after scoring
python3 holdout_stage2.py bootstrap PA --period full   # t without assuming independence
python3 holdout_stage2.py dsr PA --period full         # deflated Sharpe vs best of 131
python3 holdout_stage2.py regime PA --lookback 480     # trendline edge vs trend beta
```

`select` refuses to overwrite an existing frozen file without `--force`, and
records `forced: true` if used. `score` warns if any trade file changed between
freezing and scoring. The ordering is the whole point: run them as separate
acts, with a commit in between.

## The scan notebook

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
4. `SYMBOLS = None` for the full run. Roughly 3 to 4 hours for 131 symbols.

Outputs land in `results/` with a datestamp.

**Known issue:** the notebook still carries its own hardcoded 15-symbol `TICKS`
dict, the same defect fixed in `batch_backtest.py` (defect 3 above). It should
import from `instruments.py` before any further notebook run.

## Instrument metadata

`instruments.py` maps every symbol to its full name and tick size, covering all
131 scanned instruments.

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

## Training data for the tier model

```bash
python3 make_training_data.py MGC PL PA SI HG
```

Forced to `causal=True, fill='intrabar'` so the features (touches, span, slope)
are known at entry. The old default leaked the future into the features
themselves, separate from label leakage. Train only on `FEATURE_COLS`; never feed
a `LABEL_COL`.

Given the results above, a tier model trained on this signal is fitting a
strategy with a real but sub-cost edge and no validated per-instrument
structure. Treat it as an exercise until the forward test reports.

## CSV format

`time,open,high,low,close[,volume]` — time may be epoch seconds, epoch ms, or a
datetime string. Header optional. Use full-size ratio-adjusted continuous series.

## Files

**Engine**
- `backtest_hull.py` — detector, exit engine, loader, `fill` + `causal` params.
- `instruments.py` — symbol to name and tick size mapping, all 131 verified.
- `resample_tf.py` — 1h to 4h (or any rule) resampler.

**Running backtests**
- `run_backtest.py` / `batch_backtest.py` — CLI backtests.
- `scan_trendline.ipynb` — 131-symbol scan, MAXSPAN sweep, significance counts.
- `make_training_data.py` — tier-model training set (honest defaults).

**Validation**
- `holdout_protocol.md` — stage 1, withdrawn (ran on defective data).
- `holdout_protocol_stage2.md` — stage 2 pre-registration, plus the stage 3
  span sweep record.
- `forward_test_protocol.md` — pre-registration for the forward paper test.
- `holdout_stage2.py` — selection freeze, holdout scoring, dependence and
  search-size diagnostics.
- `stats_honest.py` — block bootstrap, deflated Sharpe, Newey-West OLS.
- `random_entry_control.py` — monkey control (honest defaults).
- `tick_sanity.py` — stop distance in ticks, cost per bet, exclusion sensitivity.
- `span_sweep.py` — span configs by gross edge and cost per bet.

**Infrastructure**
- `check_orders.py`, `DEPLOY.md`, `docker-compose.yml` — live/paper infra.
- `results/` — datestamped scan output and frozen selection files.
