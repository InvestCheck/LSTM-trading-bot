> ## WITHDRAWN — 22 Aug 2026
>
> **This protocol ran exactly as registered, and its results are void anyway.**
> Two independent problems, either of which is sufficient on its own.
>
> **1. The data was defective.** The trades were generated before a price
> rounding defect in `backtest_hull.py` was found (bias source 4 in the main
> README). `entry` and `stop` were stored as `round(x, 4)` and read back by the
> exit engine, quantising the price grid to 100 ticks on instruments priced near
> 0.0068. J7 and J1 — the two instruments this protocol reports as PASS — are
> exactly the two the defect corrupted. J7 fell from +342.4R to +82.7R once
> fixed, so its headline was 76% artifact.
>
> **2. The selection was contaminated.** The four instruments were chosen
> because their *full-sample* t exceeded 3, and the full sample contains the
> post-2020 holdout. The share of the selection statistic that is literally the
> holdout is `sqrt(n_post / n_full)`: 0.62 for J7, 0.61 for J1. Roughly 60% of
> the evidence that selected them was the data used to confirm them. The
> "Honest caveat" section below anticipated this in general terms but
> substantially understated the magnitude.
>
> On pre-2020 data alone — what a trader standing on 2020-01-01 would have had —
> J1 (t 2.36) and ZR (t 3.06) would never have entered the survivor set at all.
>
> The successor is `holdout_protocol_stage2.md`, which runs the selection on
> pre-cutoff data first and freezes the surviving list before scoring. It
> selected nothing.
>
> The associated result files in `results/` are withdrawn and must not be cited.
> Both this document and those files are kept rather than deleted so the
> correction is auditable. **Everything below this block is unchanged from its
> original commit** and can be verified with
> `git show <original-hash>:holdout_protocol.md`.

---

# Holdout protocol — trendline-walk survivors

**This document must be committed before `holdout_test.py` is run for the first
time.** Its only purpose is to fix the hypothesis, the parameters, and the pass
criteria in advance, so that whatever comes out cannot be reinterpreted after the
fact. If the commit timestamp on this file is not earlier than the commit
timestamp on the first results file, the test is worthless and should be
discarded.

## What is being tested

The costed 131-instrument scan (10 Aug 2026, `MAXSPAN=1200`, 1 tick round-trip
slippage) produced a **net negative portfolio**: mean PF 1.03, total −3,062R.
72 of 131 instruments were net positive, but with 131 simultaneous tests most of
those are noise. Applying a t-test on mean R per instrument, four cleared t > 3:

| symbol | instrument | trades | PF | avg R | total R | t |
|---|---|---|---|---|---|---|
| J7 | E-mini Japanese Yen | 1,460 | 1.65 | +0.23 | +342.4 | 5.87 |
| J1 | Japanese Yen | 1,383 | 1.43 | +0.16 | +224.3 | 4.25 |
| PA | Palladium | 621 | 1.47 | +0.19 | +115.3 | 3.78 |
| ZR | Rough Rice | 318 | 1.66 | +0.24 | +75.0 | 3.48 |

**J7 and J1 are the same underlying** (E-mini and full-size JPY futures). This is
three independent bets, not four. The realised correlation between their trade
returns is reported by the test script and is expected to be high.

At t > 3 across 131 tests, the expected number of false positives by chance is
well under one, so four survivors is above chance. That is a real observation and
should not be dismissed. It is also not evidence that any individual one of them
is real, because the four were *selected* for being extreme. That selection is
exactly what this protocol exists to test.

**Hypothesis under test:** the edge observed in J7, J1, PA and ZR is a property of
those instruments, not an artefact of having searched 131 of them.

## Frozen parameters

No parameter below may be changed for any reason once this file is committed. If
any of them is changed, the run is a new experiment and this protocol does not
apply to it.

```
detector      backtest_hull.run()
causal        True
fill          'intrabar'
MAXSPAN       1200
CAP           1e12          (risk cap off)
tol           0.0015
touch_band    0.0005
brk_tol       0.0002
SPANDAYS      7
K             3
MINSPAN       168
MINTOUCH      3
TGAP          6
WARMUP_DAYS   60
slip_ticks    1             (per-instrument tick from instruments.py)
data          FirstRateData full-size ratio-adjusted continuous, 1H
```

Exit engine unchanged: 200 EMA wick ratchet gated at 0.5R, breakeven at +1R,
21 EMA close trail, parabolic exit at 3.5×ATR from the 21 EMA.

## Test 1 — Time split (weak)

Run the frozen rule once over the full history, then partition the resulting
trades by entry timestamp at **2020-01-01**. No refitting. The pre-2020 data
serves as warmup for the post-2020 period, which is what a live trader would
have had.

**This is quasi-out-of-sample at best and must be reported as such.** All 18.5
years were visible during development. A pass here is weak evidence; a failure
here is strong evidence against.

### Power, computed in advance

Roughly 35% of the history falls after 2020-01-01. Deriving per-trade dispersion
from the published t-statistics and projecting forward:

| symbol | expected holdout trades | expected t if the effect is entirely real |
|---|---|---|
| J7 | ~513 | 3.48 |
| J1 | ~486 | 2.52 |
| PA | ~218 | 2.24 |
| ZR | ~112 | 2.06 |

**ZR and PA are underpowered at the chosen threshold.** Even if their edge is
completely real, ZR is expected to land almost exactly on t = 2, meaning roughly
a coin flip on whether it passes. A ZR failure therefore carries much less
information than a J7 failure, and must not be read as though it carried the
same weight.

### Pass criteria — fixed now

Per instrument, on the post-2020 partition:

- **PASS:** PF > 1.2 **and** t > 2.0
- **MARGINAL:** PF > 1.1 and t > 1.5, but not meeting PASS
- **FAIL:** anything else

### Interpretation — fixed now

- **J7 fails →** the strongest of the four does not survive even a weak split.
  Conclude the four survivors are a selection artefact. Stop.
- **J7 passes, PA and ZR fail →** consistent with a JPY-specific effect and with
  PA and ZR being noise, but also consistent with underpowering. Not resolvable
  here; proceed to Test 2 and Test 3 for JPY only.
- **All four pass →** encouraging but not sufficient, because the window was
  visible during development. Proceed to Test 3. Do not describe this as
  out-of-sample validation.
- **PA or ZR passes while J7 fails →** treat as noise, not as a finding. This
  ordering has no mechanism behind it.

## Test 2 — Cross-instrument (stronger)

If a JPY effect is real, the mechanism should not be unique to one contract
specification. Run the identical frozen rule on FX instruments **not** among the
four survivors:

```
RY    Euro / Yen
PJY   Pound / Yen
E6    Euro FX
B6    British Pound
A6    Australian Dollar
```

RY and PJY are yen crosses, so they carry the yen leg. E6, B6 and A6 are FX
without a yen leg and act as the control group within the control group.

### Pass criteria — fixed now

- **SUPPORTIVE:** at least one of RY or PJY has PF > 1.15 over the full history
- **UNSUPPORTIVE:** both yen crosses at PF < 1.05
- **CONCERNING:** the yen crosses are flat while E6, B6 or A6 look strong, which
  would indicate whatever is being picked up is not yen-related at all

A result where J7 and J1 work and no other FX instrument shows anything is
**evidence for overfitting**, not evidence for a JPY effect. That is the single
most likely outcome and it must be reported plainly if it occurs.

## Test 3 — Forward paper (the only clean test)

Only run if Tests 1 and 2 do not already falsify the hypothesis.

- Start date fixed and recorded before the first order.
- Instruments: whichever survived Tests 1 and 2, and nothing else.
- Frozen rule via the IBKR bracket-order path. No parameter changes, no
  instrument additions, no early stopping.
- **Minimum six months before any result is read.** Checking early and stopping
  on a good week reintroduces exactly the selection this whole protocol exists to
  remove.

## What gets published either way

Whatever the outcome, the results go into the repository README with the same
prominence as the existing figures. A failed holdout, published, is worth more
than an unpublished pass — it is the difference between having tested the
hypothesis and having looked for a reason to keep it.

If the hypothesis fails, the honest summary is: *a 131-instrument search produced
four apparent survivors, and a holdout test showed them to be selection
artefacts.* That is a complete and useful result.

---

**Committed:** _(fill in commit hash and date before running anything)_
