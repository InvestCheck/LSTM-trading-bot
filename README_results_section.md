## Result

A 131 instrument search over hourly futures. **No individual instrument shows an
edge that survives correction for the size of the search.** The pooled signal
across the executable universe does carry real information, and is positive net
of one tick round trip slippage, but it is small and commissions are not yet
modelled.

Both halves of that sentence matter. They answer different questions, and this
project spent most of its life conflating them.

### Four sources of optimistic bias, all now corrected

| | defect | effect |
|---|---|---|
| 1 | non causal pivot detector | lookahead in signal generation |
| 2 | entry fill silently dropped losing trades | survivorship in the trade set |
| 3 | missing tick table, zero cost on most instruments | costs understated |
| 4 | **price rounding on low priced instruments** | see below |

The fourth was found 22 Aug 2026. `backtest_hull.py` stored `entry` and `stop`
as `round(x, 4)`, and the exit engine read those rounded values back while
computing `R` from the unrounded ones. On an instrument priced near 0.0068 with
a 1e-6 tick, four decimal places quantises the price grid to 100 ticks.
Confirmed by A/B on matched synthetic series: gold priced data is bit identical
either way, yen priced data moves avgR by 0.05R and changes the trade count.

The two instruments affected were the two the published result rested on:

| | before fix | after fix |
|---|---|---|
| J7 | 1,460 tr, +342.4R, avgR +0.23, PF 1.65 | 1,397 tr, +82.7R, avgR +0.06, PF 1.15 |
| J1 | 1,383 tr, +224.3R, avgR +0.16, PF 1.43 | 1,291 tr, +98.6R, avgR +0.08, PF 1.19 |
| PA | 621 tr, +115.3R, avgR +0.19, PF 1.47 | unchanged |
| ZR | 318 tr, +75.0R, avgR +0.24, PF 1.66 | +76.0R, avgR +0.24, PF 1.67 |

J7's headline was 76% defect. PA and ZR trade at price levels where four decimal
places are invisible, which is why they did not move.

**All stage 1 holdout results are withdrawn.** They were computed on the
defective data, and the JPY instruments they turned on are exactly the ones the
defect touched.

### No instrument survives a clean selection

Stage 1 split each survivor's trades at 2020-01-01 and scored the second half.
That test was contaminated: the survivors were chosen on *full sample* t, and the
full sample contains the holdout. The share of the selection statistic that is
literally the holdout is `sqrt(n_post / n_full)`, which is 0.62 for J7 and 0.61
for J1. Roughly 60% of the evidence that chose them was the data used to confirm
them.

Stage 2 (`holdout_protocol_stage2.md`, registered before the run) fixes the
ordering: rank on pre 2020 data only, apply a Bonferroni threshold for 131 tests
of t > 3.55, freeze the surviving list to disk, then score post 2020 once.

Ranking on 2020-01-01, instruments with n >= 100:

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
nothing to score.

Two follow ups confirm it rather than rescue it.

**Serial dependence is not the problem.** A stationary block bootstrap
resampling whole calendar blocks from the demeaned trade series gives an
inflation factor of 1.00 for PA and 0.83 for ZR across month, quarter and year
blocks. The individual t statistics are correctly calibrated. This was a stated
hypothesis of the project and it is rejected.

**The leaders are not leaders.** Across the 78 clean instruments the cross
sectional spread of t is 1.43, wider than the 1.0 expected under pure noise.
Since the individual statistics are calibrated, that excess is genuine
heterogeneity in edge, implying a true effect sd of 1.02 and an empirical Bayes
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

That block has median t of −2.57 and accounts for essentially the entire
portfolio deficit. `tick_sanity.py` reports it per instrument and prints the
full sensitivity column, so the exclusion threshold cannot be chosen to flatter
the total. The criterion is mechanical rather than performance based: a stop
narrower than the round trip cost cannot be executed as designed.

Slippage sensitivity over the whole book, 70,187 trades:

| slip | total R |
|---|---|
| 0 | +3,798.3 |
| 0.5 | +116.8 |
| 1 | −3,564.2 |
| 2 | −10,926.8 |

Breakeven is at 1.03 ticks round trip, **with no commissions modelled.** That is
what you pay on a one tick wide market filled exactly at the touch, so the whole
book is at best marginal and commissions push it under. On the micro contracts
(MGC, MES, MNQ, M2K, MBT) a $4 round trip commission can exceed 5% of the bet on
its own.

### The signal is real, and small

The entry is not noise. `random_entry_control.py` matches trade count, stop size
and exit engine, randomising only entry bar and direction:

- On 12 instruments drawn by fixed seed from the clean subset, chosen without
  reference to performance: strategy +240.3R against a random mean of −17.3R
  (sd 95.8), with 0.4% of 500 random runs beating it, z = 2.7.
- An earlier run on the four gross leaders gave z = 6.3. **That number is
  inflated and should not be quoted.** The instruments had been selected on
  performance, so a selected maximum was being compared against an unbiased
  random arm.

Gross of costs, the pre 2020 median t across 92 instruments is +1.31, against
+0.37 costed. A median is not a selected maximum, so it is not subject to the
multiplicity problem that killed PA. The signal has broad predictive content and
is roughly half the size of what it costs to harvest.

### Longer trendlines give better signals, not bigger ones

Span configs on the executable subset. One zero slippage pass per config with
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
produces better signals rather than larger ones, which supports the top down
thesis by a different route than the one proposed.

**The previous claim that unbounded span is worse is withdrawn.** It read
−8,860R on 107,867 trades. On the corrected build with unexecutable instruments
excluded it is +1,512R net at one tick. Both the rounding defect and the ZQ
class contracts were driving that conclusion.

### What is and is not supported

Supported:

- The entry signal carries real information (z = 2.7 on an unselected sample).
- Serial dependence between trades is not inflating these statistics.
- Longer span floors improve per trade edge monotonically.
- The pooled signal on the executable subset is positive net of one tick round
  trip slippage.
- The reported portfolio loss is driven by contracts where execution cost
  exceeds the bet size, not by the signal.

Not supported:

- Any claim about a specific instrument. Nothing clears a multiplicity corrected
  threshold, and PA at 3.47 against 3.55 is a miss that cannot be promoted by
  re reading data it has already been measured on.
- Any claim about JPY. That result was a rounding artifact.
- Any claim about a metals cluster. PA, PL, MGC, HG and GC ranking near the top
  is what correlated instruments do under the null.
- Any claim of out of sample validity. Every number above is full sample on data
  used repeatedly for selection. The span result is explicitly exploratory.

Not yet modelled: commissions, exchange and clearing fees, and the capacity
constraint of holding positions in roughly 90 contracts at once.

The only clean test remaining is forward paper trading against a configuration
fixed in advance. See `forward_test_protocol.md`.
