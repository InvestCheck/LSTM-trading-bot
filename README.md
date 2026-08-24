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

**The pooled signal is nonetheless real, and about half of it survives
execution costs.** A random-entry control on instruments chosen without
reference to performance gives z = 2.7. At the best span config, with a
trade-level cost floor applied, the pooled edge is gross avgR +0.072, falling
to **+0.040** after one tick round-trip slippage, with a dependence-adjusted
**t of +4.00** across 16,796 trades. Commissions take it to roughly +0.025 to
+0.033, **t of about 2.5 to 3.0**. It is stable across a 2020 split and does
not depend on any single instrument. It is also entirely full-sample and has
never been traded.

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

Split at 2020-01-01, gross avgR in each half:

| span | pre | post |
|---|---|---|
| 168..1200 | +0.0654 | +0.0607 |
| 720..4320 | +0.0673 | +0.0743 |
| 2160..17520 | +0.0801 | +0.0743 |
| 168..unbounded | +0.0687 | +0.0652 |

Every config, both halves, lands between +0.060 and +0.080. Nothing here looks
like a single regime. This is **not** a holdout — post-2020 has been used for
selection and contamination analysis throughout this project — and speaks only
to stability, not validity.

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

### A trade-level cost floor, and what it is worth

The 10% cost rule that excludes whole instruments (`2 ticks / median R > 0.10`)
had never been applied to individual trades. Within any instrument, stop width
varies, so cost varies: a 25-tick stop pays 8% of the bet, a 128-tick stop pays
1.6%. Bucketing by stop width (`stop_width.py`):

| stop (ticks) | share | cost/bet | gross avgR | net avgR |
|---|---|---|---|---|
| 0–20 | 13.4% | 17.5% | **+0.1173** | **−0.0578** |
| 20–32 | 12.9% | 7.9% | +0.1124 | +0.0337 |
| 32–48 | 13.6% | 5.1% | +0.0891 | +0.0379 |
| 48–64 | 10.0% | 3.6% | +0.1006 | +0.0642 |
| 64–96 | 13.7% | 2.6% | +0.0693 | +0.0435 |
| 96–128 | 8.5% | 1.8% | +0.0515 | +0.0332 |
| 128+ | 27.9% | 0.8% | +0.0416 | +0.0341 |

Gross avgR is **not** flat: tight stops near structure carry the most edge per
unit of risk. But the narrowest bucket has the best gross edge in the sample and
still loses money, because it pays 17.5% per bet.

A 20-tick floor is `2/20`, which is the same 10% rule applied one level down.
It keeps 87% of trades and moves the result substantially:

| | no floor | 20-tick floor |
|---|---|---|
| trades | 19,426 | 16,796 |
| gross avgR | +0.0779 | +0.0719 |
| median stop | 64 ticks | 78 ticks |
| net avgR @ 1 tick | +0.0264 | **+0.0396** |
| t_adj (weakest block) | +2.68 | **+4.00** |

The floor helps twice: it drops the trades that cannot pay their own cost, and
the surviving median bet is wider, which also lowers commission per trade.

**An honesty note on the floor.** The 10% criterion predates this test, and the
execution argument is independent of PnL: a stop narrower than the round-trip
cost cannot be filled as designed. But the decision to apply it at trade level
was made *after* seeing that the 0–20 bucket was net negative. Information
flowed from the data to the choice. That makes this a mechanically justified
rule applied after observing that it helps, which is weaker than a
pre-registered one, and it is described that way deliberately.

Raising the floor further does not help. At 48 ticks net avgR is +0.0411 against
+0.0395, but the sample drops 30% and t falls to +4.88 naive. There is also no
principled justification above 20 — choosing 48 because it maximises avgR would
be fitting.

### The edge is broad, not a few instruments

A pooled t says nothing about distribution. Leave-one-out across all 102
instruments (`jackknife.py`, 2,000 resamples):

- full book **t_adj +4.06**
- worst single exclusion: without CNH, **+3.77**
- best single exclusion: without AD, +4.40
- 63 of 102 instruments positive, against ~51 expected under a null

No instrument is load-bearing. Top contributor E7 is 9.8% of net R and the top
ten are 64%, across 102 names.

The same tool reports a drop-the-top-k column, which falls to +1.67 at k=10 and
zero at k=20. **That column is biased and should not be read as fragility.** It
selects on outcome, so it removes lucky draws along with real ones; a genuinely
broad edge collapses under it mechanically. Leave-one-out is the informative
view.

### Stability across time

With the floor applied, split at 2020-01-01: gross avgR **+0.0712 pre** and
**+0.0729 post**, on 10,353 and 6,443 trades. The floor did not select a regime.
This is a stability check, not a holdout — post-2020 has been used throughout
this project.

### How significant is the pooled edge, honestly

The naive pooled t at 2160:17520 is +10.63 gross. **That figure is inflated and
should not be cited.** It treats all 19,426 trades as independent draws, but the
strategy holds correlated positions across many instruments at once, so a month
in which metals trended is one event expressed dozens of times.

A cluster bootstrap resamples whole calendar blocks across all 103 instruments
together, keeping simultaneous trades bound to each other:

| blocks | count | gross t_adj | net@1 t_adj | net p |
|---|---|---|---|---|
| month | 218 | +8.06 | +2.75 | 0.0076 |
| quarter | 73 | +7.84 | **+2.68** | 0.0060 |
| year | 19 | +9.12 | +3.37 | 0.0016 |

Cross-instrument correlation deflates the statistic by 1.07x to 1.36x, less than
expected. The number that matters is the **weakest net figure, +2.68**, not the
gross one and not the best block length.

Two things pull it lower still. This config was chosen as the best of four on
gross avgR, so correcting for four tests puts it near +2.2 (an overcorrection,
since the four configs are correlated rather than independent, but the honest
range is +2.2 to +2.7 rather than a clean +2.68). And commissions, below, take
another large bite.

### Commissions

Not previously modelled anywhere. `commissions.py` carries verified tick values
for 40 contracts and **raises rather than defaulting to zero** on the other 55 —
a zero default is exactly what caused bias source 3.

With the 20-tick floor the median bet is 78 ticks, so commission falls too.
Across the 40 verified contracts: median **0.61%**, mean 1.02%, worst 3.18%.
Applied to net avgR of +0.0396:

| universe assumption | net avgR | t_adj |
|---|---|---|
| median contract | +0.0335 | **+3.38** |
| mean contract | +0.0294 | +2.97 |
| micro-heavy | +0.0078 | +0.79 |

Correcting for having chosen the best of four span configs takes +4.00 to
roughly +3.5, and the micro-heavy case is no longer negative.

**Sensitivity to the unverified contracts.** 64 of 102 executable symbols, and
54.4% of trades, have no verified tick value. Rather than guess them,
`commission_sensitivity.py` applies exact commissions to the verified 38 and
sweeps an assumed rate across the rest:

| assumed cost on unverified | net avgR | net total | t_adj |
|---|---|---|---|
| verified median 0.61% | +0.0314 | +527.6 | +3.18 |
| verified mean 1.02% | +0.0284 | +476.9 | +2.87 |
| 2.00% | +0.0212 | +355.7 | +2.14 |
| verified worst 3.18% | +0.0125 | +209.7 | +1.26 |
| 5.00% | −0.0009 | −15.4 | −0.09 |

**Breakeven is 4.88%** — worse than any contract in the verified set. The
unverified names are overwhelmingly full-size CME FX (DX, E1, RP, RY, J1, AD,
J7, CNH), Eurex bonds and index (FGBL, FGBX, FBTP, FOAT, FDAX, FESX) and ICE
softs (G, CT, BZ), which are the cheap end. Almost none are micros. The
plausible band is therefore **t_adj +2.1 to +3.2**, centred near +2.9.

The distribution is flat: it takes 38 symbols to cover 85% of unverified
trades, so there is no small set of lookups that resolves this.

Two inputs remain estimates. The **$1.45/side exchange fee** for standard CME
contracts is the load-bearing one — it sits under all 103 contracts including
the 38 already verified — and comes from IBKR's collapsed fee tables rather than
an account statement. And the 64 unverified tick values, which the sensitivity
above shows cannot flip the sign but do set the width of the band.

---

## What is and is not supported

Supported:

- The entry signal carries real information (z = 2.7 on an unselected sample).
- Serial dependence between trades is not inflating these statistics.
- Longer span floors improve per-trade edge monotonically.
- The pooled signal on the executable subset is positive net of one tick
  round-trip slippage, at a dependence-adjusted t of +4.00 with a trade-level
  cost floor, roughly +3.5 after correcting for four span configs.
- After commissions the plausible band is t_adj +2.1 to +3.2.
- The edge is broad: leave-one-out across 102 instruments never falls below
  +3.77, and 63 of 102 instruments are positive.
- Gross per-trade edge is stable across a 2020 time split in every config, with
  and without the floor.
- Trade outcome shows no exploitable structure in signal-time features. On PA,
  the best of 2,000 random filters improved net avgR by +0.26 with no
  information at all (`filter_control.py`); any fitted filter must clear that
  bar, and none has.
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
  data used repeatedly for selection. The span result is explicitly exploratory,
  and the 2020 split shows stability rather than validity.
- **Any claim that this is tradeable.** The result has never been traded, the
  execution path has never been run live, and the exchange-fee component of the
  cost model is an estimate rather than a measurement.
- **Any per-instrument or per-setup filter.** A random-filter control shows the
  search space is large enough that fitted filters are indistinguishable from
  noise on this data, and no clean holdout remains to check one against.

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
- **Commissions are only partially modelled.** `commissions.py` covers 40 of 103
  executable contracts. The sensitivity analysis shows the remainder cannot flip
  the sign (breakeven 4.88% against a worst verified contract of 3.18%) but does
  set the width of the band. The **exchange-fee estimate is the larger open
  item**, since it applies to every contract including the verified ones, and is
  settled cheaply from an account statement rather than a spec table.
- **The trade-level cost floor was applied after observing that it helps.**
  Mechanically justified, not pre-registered. See the note in the span section.
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

# trade-level cost floor. --min-ticks 20 is the 10% rule (2/20) applied to
# individual trades. Mechanical, not tuned; do not raise it to chase total R.
python3 span_sweep.py --data-dir DATA_DIR --min-ticks 20 --cluster-boot 5000

# stop width vs edge: is the cost saving real, or is it trading edge for cost?
python3 stop_width.py

# is the edge broad or a few instruments? leave-one-out is the honest column
python3 jackknife.py --min-ticks 20 --boot 2000

# how bad would the unverified contracts have to be to kill the result?
python3 commission_sensitivity.py --min-ticks 20 --boot 5000

# the monkey control for filters: how much does a RANDOM filter improve things?
python3 filter_control.py PA --sims 2000
python3 filter_control.py PA --sims 2000 --my-filter "touches>=4,span_bars>=3000"

# pooled cluster bootstrap: t without assuming trades are independent across
# instruments. Reports gross and net@1 across month/quarter/year blocks.
python3 span_sweep.py --data-dir DATA_DIR --configs 2160:17520 --cluster-boot 5000

# commission table: tick values, round-trip cost, share of a 64-tick bet
python3 commissions.py
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
- `span_sweep.py` — span configs by gross edge and cost per bet; trade-level
  cost floor; pooled cluster bootstrap across instruments.
- `stop_width.py` — edge and cost by stop width, and the cumulative effect of a
  trade-level floor.
- `jackknife.py` — leave-one-out and drop-the-top-k across instruments.
- `filter_control.py` — random-filter control. Builds a null matched to your
  filter's own retention rate, because a null at a different retention rate
  flatters tight filters.
- `commissions.py` — tick values and all-in round-trip costs. Raises on
  unverified symbols rather than defaulting to zero.
- `commission_sensitivity.py` — sweeps an assumed cost across the unverified
  contracts and reports the breakeven.

**Execution and infrastructure**
- `live_ibkr.py` — IBKR bracket-order execution path, validated against the exit
  engine. Never run live.
- `sizing.py` — position sizing.
- `trade_logger.py` — trade record persistence.
- `check_orders.py` — order reconciliation.
- `feature_schema.py` — feature/label column definitions for the tier model.
- `example_usage.py` — minimal worked example.
- `DEPLOY.md`, `docker-compose.yml`, `requirements.txt` — deployment.
- `results/` — datestamped scan output and frozen selection files. **Read
  `results/README.md` first**: the stage 1 holdout output in there is withdrawn,
  and the 10 Aug notebook scan predates the rounding fix.

## Attribution

Research direction, strategy design, execution infrastructure and all decisions
are mine. Anthropic's Claude was used substantially as a research assistant:
writing analysis tooling (`stats_honest.py`, `holdout_stage2.py`,
`tick_sanity.py`, `span_sweep.py`), auditing the backtest for bias, and drafting
protocol and documentation text. Commit co-authorship reflects this and is left
in place deliberately rather than scrubbed.

Two things worth noting about that collaboration, because they bear on how much
weight to give any single claim in this document. Several of the assistant's
stated hypotheses were tested and **rejected** by the data — that trade-level
serial dependence was inflating the t-statistics (bootstrap says no), that
dividing t by the cross-sectional sigma was the right multiplicity correction
(the calibration evidence says empirical Bayes shrinkage is), and that longer
span floors would lower per-trade edge (it rises). Each is recorded above or in
the protocols rather than quietly dropped. And one methodological error was made
and caught: an early random-entry control was run on instruments already selected
for performance, producing an inflated z = 6.3 that is flagged as uncitable in
the main text.
