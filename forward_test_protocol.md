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
                    2 * tick / median(R_px) <= 0.10, measured on the
                    data vintage below and FROZEN as a symbol list
weighting           equal risk per trade, 1R per position, no scaling
position limit      no cap; every signal is taken
```

The universe is frozen as an explicit symbol list at the bottom of this file,
not recomputed at trade time. Recomputing it would let the eligible set drift
with recent volatility, which is a live selection effect.

## Data vintage

Every backtest figure in this document comes from one archived download:

```
source        FirstRateData 1 hour continuous ratio adjusted files
last bar      2026-09-08 18:00
archive       DATA_DIR_2026-09-08.tgz
sha256        5dce6ca23978bc65df411b9428643467eeb97becf75681330dbbd3c44440de2c
engine        backtest_hull.py at commit bd51058
trade files   backtests/trades_*.csv, regenerated from this archive with
              batch_backtest.py --minspan 2160 --maxspan 17520
```

An earlier download of the same history (last bar 2026-06-19) could not be
reproduced from this one: the vendor revised its roll adjustments in between.
At the frozen config, 87 to 93% of trades matched between the two vintages on
GC, ES and ZN, and the universe changed by one swap (B in, US out). So roughly
one trade in ten depends on which download of the same market history is used.
This is recorded as a finding in its own right, and it drives the scoring rule
below.

## Live engine requirements

These are part of the frozen configuration. A live engine that departs from any
of them is not running this protocol.

```
history             each instrument's line detection sees at least MAXSPAN
                    (17520) bars of ratio adjusted hourly history before its
                    first live signal; the 60 day warmup alone is not enough
                    for a line to reach the span floor
span filter         applied by the same code path as the backtest, not a
                    reimplementation
protective orders   stop and target children are GTC, never DAY
logging             every order, fill and roll is logged with a timestamp;
                    each trade row records the engine assumed price and the
                    actual fill price
```

## Contract rolls

The backtest ran on ratio adjusted continuous data, so a position held across a
roll was implicitly rolled. The live test mirrors that:

```
trigger             close of the session 5 trading days before the earlier of
                    first notice day and last trade date of the held contract
action              close the held contract and open the same direction and
                    size in the next contract; the roll is not an exit
stop                scaled by the ratio of new to old contract price at the
                    roll fills, preserving the stop distance in ratio terms
scoring             realised R is computed on the price path spliced by the
                    same ratio, so a rolled trade is scored as the backtest
                    would score it
costs               slippage and commission on both roll legs are charged to
                    that trade
new entries         only in the active contract; no new entry in a contract
                    inside its roll window
```

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

Measured trade rate, frozen universe, 2023-09-08 to 2026-09-08: about 487
trades per six months. 400 trades should therefore
arrive before six months, so the six month clock is expected to bind and the
expected end date is six months after the first recorded trade plus any logged
gaps. If 400 trades have not been reached at six months, the test continues
until they are.

A 12 month duration was considered before starting and declined. That decision
is recorded here so it cannot be revisited after seeing results.

If the run is interrupted for operational reasons (data outage, broker issue),
the gap is logged and the clock is extended by the length of the gap. Trades are
not backfilled.

## Pass criteria — fixed now

The scored trade set is the trades the live engine generated and logged at the
time, on the bars it actually had. It is never regenerated by rerunning the
engine on a later data download: given the vintage sensitivity above, a rerun
would score a different set of trades.

All criteria use net R per trade, after slippage and commissions, on the pooled
trade set. The three categories cover every possible outcome.

- **PASS**: net avgR > 0 and pooled t > 2.0
- **INCONCLUSIVE**: net avgR > 0 and pooled t <= 2.0
- **FAIL**: net avgR <= 0

Gross avgR is reported alongside but is not a criterion.

Pooled t is computed on net R with a stationary block bootstrap over calendar
quarters, not the naive iid t. The naive figure may be reported alongside but is
not the criterion. Prior bootstraps on this strategy returned inflation factors
near 1.0, so the two should agree; if they diverge materially, the bootstrap
governs.

### Expected outcome, stated in advance

The backtested gross avgR at this config is +0.0806 (17440 trades, frozen
universe) with a cost of roughly 3.1%
of the bet from slippage alone. Adding commissions, the expected forward net
avgR is in the region of +0.03 to +0.05R, and at the expected ~490 trades that
gives a pooled t of roughly 1.0 to 1.6. **The most likely outcome is therefore
INCONCLUSIVE, not PASS.** Six months is probably underpowered to distinguish a
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

70 instruments, generated once with the command below on the trade files from
the data vintage above:

```
A6 AD B B6 BZ CL CNH CT DC DX E1 E6 E7 ES EW FBON FBTP FCE FDAX FDXM FESX FGBL
FGBM FGBX FOAT FTI FTUK FXXP G GC GF HE HG HO J1 J7 KE LE MFS MGC MME MP N6 NG
NIY NKD NOK NQ PA PL RB RP RS RTY RY SB SEK SI SIR TN UB XC YM ZC ZF ZL ZM ZN
ZS ZT
```

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
