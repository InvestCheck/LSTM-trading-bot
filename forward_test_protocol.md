# Forward test protocol

**This document must be committed before the first paper trade is recorded.** If
the commit timestamp on this file is not earlier than the first row of the trade
log, the test is worthless and should be discarded. Same rule as every prior
stage in this project.

## Why this is the only test left

Every result in `README.md` is full sample. The 131 instrument universe has been
used for instrument selection, for contamination analysis, for the span sweep,
and for four rounds of defect hunting. There is no held out slice of it that has
not informed a decision somewhere in this repo, and the 2020-01-01 split in
particular has been examined repeatedly and cannot be reused.

Forward data is the only data this project has not already spent.

## Hypothesis

The trendline walk signal, applied as an equally weighted portfolio across the
executable universe at a long span floor, produces a positive per trade edge net
of realistic transaction costs.

Note what is **not** being tested: no claim about any individual instrument. The
stage 2 selection found nothing clearing a multiplicity corrected threshold and
that result stands. This tests the pooled signal only.

## Frozen configuration

```
span floor          MINSPAN 2160 bars
span ceiling        MAXSPAN 17520 bars
fill                intrabar
causal              True
warmup              60 days
universe            every instrument in instruments.py where
                    2 * tick / median(R_px) <= 0.10, measured on data
                    through 2026-06-19 and FROZEN as a symbol list below
weighting           equal risk per trade, 1R per position, no scaling
position limit      no cap; every signal is taken
```

The universe is frozen as an explicit symbol list at the bottom of this file,
not recomputed at trade time. Recomputing it would let the eligible set drift
with recent volatility, which is a live selection effect.

## Costs

Paper fills are recorded at the price the engine assumes, and costs are applied
in post as:

```
slippage      1 tick per side (2 ticks round trip)
commission    actual broker rate per contract, round trip, converted to R
              using the contract's tick value and the trade's R_px
```

Commissions were not modelled anywhere in the backtest and must be included
here. On the micro contracts a $4 round trip can exceed 5% of the bet on its
own, which is larger than the entire measured edge.

Realised slippage is also recorded per fill so the 1 tick assumption can be
checked against actual fills rather than assumed. This is the one calibration
input the backtest never had.

## Duration and stopping rule

Minimum six months from the first recorded trade, or 400 trades, whichever comes
later. **The test may not be stopped early for any reason, including a good
result.** An early stop on a favourable run is the same error as selecting the
maximum of 131 instruments.

If the run is interrupted for operational reasons (data outage, broker issue),
the gap is logged and the clock is extended by the length of the gap. Trades are
not backfilled.

## Pass criteria — fixed now

On the pooled trade set, net of slippage and commissions:

- **PASS**: gross avgR > +0.05 and pooled t > 2.0 and net total R > 0
- **INCONCLUSIVE**: net total R > 0 but t < 2.0
- **FAIL**: net total R <= 0

Pooled t is computed with a stationary block bootstrap over calendar quarters,
not the naive iid t. The naive figure may be reported alongside but is not the
criterion. Prior bootstraps on this strategy returned inflation factors near
1.0, so the two should agree; if they diverge materially, the bootstrap governs.

### Expected outcome, stated in advance

The backtested gross avgR at this config is +0.0779 with a cost of roughly 3.1%
of the bet from slippage alone. Adding commissions, the expected forward net
avgR is in the region of +0.03 to +0.05R, and at 400 trades that gives a pooled
t of roughly 1.0 to 1.5. **The most likely outcome is therefore INCONCLUSIVE,
not PASS.** Six months and 400 trades is probably underpowered to distinguish a
+0.04R edge from zero.

That is recorded now so a subsequent INCONCLUSIVE reads as the predicted result
rather than a disappointment, and so there is no temptation to extend the run
until it crosses a threshold. If a longer run is wanted, the duration must be
raised in this document before starting, not after seeing the numbers.

## What gets published either way

The outcome goes in `README.md` at the same prominence as the existing tables.
If the result is FAIL, the honest summary is: *a signal with real gross
predictive content that cannot clear its own execution cost.* That is the most
likely finding and it is a legitimate and complete result.

## Frozen universe

_(Generate once with the command below, paste the output here, then commit this
file before the first trade.)_

```bash
python3 - << 'PYEOF'
import csv, glob, os, statistics as st
from instruments import TICKS
keep = []
for p in sorted(glob.glob("backtests/trades_*.csv")):
    s = os.path.basename(p)[7:-4]
    tick = TICKS.get(s)
    rpx = [float(r["R_px"]) for r in csv.DictReader(open(p)) if float(r["R_px"]) > 0]
    if tick and len(rpx) >= 100 and 2*tick/st.median(rpx) <= 0.10:
        keep.append(s)
print(len(keep), "instruments\n")
print(" ".join(keep))
PYEOF
```

---

**Committed:** _(fill in commit hash and date before the first trade)_
