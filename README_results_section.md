## Result: no instrument survives a clean selection

A 131-instrument search over hourly futures found no trendline-walk edge that
holds up once the search itself is priced in. Four apparent survivors were
identified in an earlier build. Two were an arithmetic defect. The other two
fail a multiplicity-corrected threshold on the data available before the
holdout period. **Nothing was selected, so there was nothing to score.**

Costed portfolio over all 131 instruments: 70,187 trades, **−3,564.2R**,
average −0.051R per trade, at 1 tick round-trip slippage.

### The fourth source of bias

Three sources of optimistic bias were documented in the previous build: a
non-causal pivot detector, an entry fill that silently dropped losing trades,
and a missing tick table that applied zero cost to most instruments. A fourth
was found on 22 Aug 2026.

`backtest_hull.py` stored `entry` and `stop` as `round(x, 4)`, and the exit
engine read those rounded values back while computing `R` from the unrounded
ones. On an instrument priced near 0.0068 with a 1e-6 tick, four decimal places
quantises the price grid to 100 ticks. Verified by A/B on matched synthetic
series: gold-priced data is bit-identical either way, yen-priced data moves
avgR by 0.05R and changes the trade count.

The two instruments affected were the two the result rested on:

| | before fix | after fix |
|---|---|---|
| J7 | 1,460 tr, +342.4R, avgR +0.23, PF 1.65 | 1,397 tr, +82.7R, avgR +0.06, PF 1.15 |
| J1 | 1,383 tr, +224.3R, avgR +0.16, PF 1.43 | 1,291 tr, +98.6R, avgR +0.08, PF 1.19 |
| PA | 621 tr, +115.3R, avgR +0.19, PF 1.47 | unchanged |
| ZR | 318 tr, +75.0R, avgR +0.24, PF 1.66 | +76.0R, avgR +0.24, PF 1.67 |

J7's headline was 76% defect. PA and ZR trade at price levels where 4dp
rounding is invisible, which is why they did not move.

**All stage 1 holdout results are withdrawn.** They were computed on the
defective data, and the JPY instruments they turned on are exactly the ones the
defect touched.

### Stage 2: selection frozen before scoring

Stage 1 split each survivor's trades at 2020-01-01 and scored the second half.
That test was contaminated: the survivors had been chosen on *full-sample* t,
and the full sample contains the holdout. The share of the selection statistic
that is literally the holdout is `sqrt(n_post / n_full)` — 0.62 for J7, 0.61
for J1. Roughly 60% of the evidence that chose them was the data used to
confirm them.

Stage 2 (`holdout_protocol_stage2.md`, registered before the run) fixes the
ordering: rank on pre-2020 data only, apply a Bonferroni threshold for 131
tests (t > 3.55), freeze the surviving list to disk, then score post-2020 once.

Result on 2020-01-01, eligible instruments with n ≥ 100:

```
PA   445 tr  PF 1.52  avgR +0.199  t 3.47
ZR   255 tr  PF 1.64  avgR +0.231  t 3.12
PL   556 tr  PF 1.37  avgR +0.144  t 2.95
MGC  528 tr  PF 1.32  avgR +0.131  t 2.49
...
J7   876 tr  PF 1.14  avgR +0.053  t 1.53   (17th)
```

Nothing clears 3.55. `results/selection_pre2020-01-01.json` records an empty
selection. Per the registered protocol, that is a complete result.

### Two instrument classes the cost model cannot represent

Of 92 eligible instruments, 14 have a median stop distance narrow enough that a
one-tick round trip exceeds 10% of the bet. On ZQ the median stop is **1.5 ticks
wide**, so cost is 135% of R and every trade opens down 1.35R before the market
moves. These are not strategy results, they are arithmetic:

```
ZQ 1.5 ticks (135% of R)   ER 2.7 (75%)   SR3 3.1 (65%)   SR1 3.6 (55%)
also dropped: EBM FGBM FGBS JB L MP PJY RM T6 US ZN ZO
```

That block has median t of −2.57 and accounts for essentially the whole
portfolio deficit. Excluding instruments on the mechanical criterion that a
stop narrower than the round-trip cost cannot be executed as designed:

| min ticks | instruments | trades | totalR | avgR |
|---|---|---|---|---|
| 0 | 130 | 70,128 | −3,566.8 | −0.051 |
| 4 | 126 | 67,557 | −485.7 | −0.007 |
| 10 | 122 | 65,397 | +75.6 | +0.001 |
| 20 | 113 | 58,564 | +648.3 | +0.011 |

So the accurate headline is not "the strategy loses money." It is **"the
strategy is flat, and four contracts where the cost model exceeds the bet size
produce the entire reported loss."** At the 10-tick cutoff, avgR of +0.001 over
65,397 trades is t ≈ 0.2. Zero, not negative.

`tick_sanity.py` reports this per instrument and prints the full sensitivity
column, so the exclusion threshold cannot be chosen to flatter the total.

### Why the leaders are not leaders

On the 78 clean instruments the cross-sectional spread of t is σ = 1.43, wider
than the 1.0 expected if every instrument were pure noise. Two explanations:
the individual t-statistics are miscalibrated, or there is genuine
instrument-to-instrument variation in edge.

A stationary block bootstrap settles it. Resampling whole calendar blocks from
the demeaned trade series gives an inflation factor of 1.00 for PA and 0.83 for
ZR across month, quarter and year blocks. Individual t-statistics are correctly
calibrated, and **serial dependence between trades is not a material problem
here** — a hypothesis this project explicitly tested and rejected rather than
assumed.

So the excess spread is real heterogeneity, implying a true-effect sd of 1.02
and an empirical Bayes shrinkage factor of 0.51 toward the median of +0.37:

| | naive t | posterior |
|---|---|---|
| PA | +3.47 | **+1.95** |
| ZR | +3.12 | +1.77 |
| PL | +2.95 | +1.68 |
| MGC | +2.49 | +1.45 |

Maximum posterior across all 78 is +1.95. Selecting the largest of 78 draws and
reading its raw t as evidence is the error; once corrected, the leader is
unremarkable.

### What can and cannot be claimed

Supported:

- No instrument in this universe shows a trendline-walk edge that survives
  correction for a 131-instrument search.
- Serial dependence between trades is not inflating these statistics.
- The reported portfolio loss is driven by a small set of contracts where
  execution cost exceeds the bet size, not by the signal.
- Median t across clean instruments is +0.37 (se 0.20, z = 1.8) — a hint of a
  weak general effect, short of significance, and not something to build on.

Not supported:

- Any claim about JPY. The stage 1 JPY result was a rounding artifact.
- Any claim about PA. A t of 3.47 against a 3.55 threshold is a miss, and PA
  cannot be promoted by re-reading data it has already been measured on. If PA
  is worth pursuing it is a new hypothesis requiring its own registration and
  its own clean test.
- Any claim about a metals cluster. PA, PL, MGC, HG and GC ranking near the top
  is what correlated instruments do under the null.

The only clean test remaining for any single instrument is forward paper
trading, registered in advance, six months minimum.
