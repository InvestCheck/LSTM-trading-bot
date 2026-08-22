# Holdout protocol, stage 2 — selection frozen on pre-cutoff data

**This document must be committed before `holdout_stage2.py select` is run for
the first time.** Same rule as stage 1: if the commit timestamp on this file is
not earlier than the commit timestamp on `results/selection_pre2020-01-01.json`,
the test is worthless and should be discarded.

`holdout_protocol.md` is not superseded and must not be edited. Stage 1 ran as
registered and its results stand as reported. This document exists because stage
1's own caveat — that all 18.5 years were visible during development — turns out
to be a much larger problem than the wording admitted.

## What stage 1 got wrong

The four symbols were selected because their **full-sample** t exceeded 3, and
the full sample contains the post-2020 partition. The fraction of the selection
statistic that is literally the holdout is `sqrt(n_post / n_full)`:

| symbol | n pre | n post | overlap with selection stat |
|---|---|---|---|
| J7 | 890 | 570 | 0.62 |
| J1 | 871 | 512 | 0.61 |
| PA | 445 | 176 | 0.53 |
| ZR | 255 | 63 | 0.45 |

Around 60% of the evidence that chose J7 and J1 was the same data used to
confirm them. A post-2020 pass is therefore partly guaranteed by construction,
and the reported holdout t-statistics of 4.40 and 3.85 cannot be read as
independent confirmation.

The corresponding pre-2020 t-statistics, which is what a trader standing on
2020-01-01 would have had, are:

| symbol | t pre-2020 | selected under Bonferroni t > 3.55? |
|---|---|---|
| J7 | 3.95 | yes |
| J1 | 2.36 | no |
| PA | 3.47 | no, borderline |
| ZR | 3.06 | no |

**J1 and ZR were never survivors on data available before the holdout.** They
entered the survivor set only because the holdout period pulled their
full-sample t across the threshold. Their stage 1 PASS and MARGINAL verdicts
answer a question that should not have been asked of them.

## What stage 2 tests

**Hypothesis:** an instrument selected using only pre-2020 data, under a
threshold that corrects for having searched 131 of them, shows an edge on
post-2020 data.

This is the same hypothesis stage 1 intended to test, run in the order that
makes the answer mean something.

## Frozen parameters

The trading rule is unchanged from `holdout_protocol.md` and may not be touched.
Every parameter in that file's "Frozen parameters" block carries over verbatim.
Stage 2 adds no trading parameters, only the selection rule below.

```
cutoff        2020-01-01        entries strictly before this go in the selection set
n_tests       131               the full scanned universe, not the survivor count
alpha         0.05
threshold     t > 3.55          two-sided Bonferroni at alpha/131
min_trades    100               eligibility floor on the PRE period
```

Selection uses the naive per-trade t, the same statistic the original scan used.
That is deliberate: the point is to correct the ordering of the experiment, not
to change the statistic mid-test. The dependence correction is applied
afterwards as a diagnostic, not as a selection filter.

## Procedure — fixed now

1. `python3 batch_backtest.py --slip 1` over all 131 symbols.
2. `python3 holdout_stage2.py select` — partitions at the cutoff, ranks on the
   pre period, writes `results/selection_pre2020-01-01.json` including the
   pass criteria and a hash of every trade file.
3. **Commit that file.**
4. `python3 holdout_stage2.py score` — scores the post period for the selected
   symbols only. The script warns if any trade file changed between steps 2
   and 4.

The script refuses to overwrite an existing selection file without `--force`,
and records `forced: true` in the file if used. A forced re-selection is not a
pre-registration and must be described as a re-run wherever it is reported.

## Pass criteria — fixed now

Unchanged from stage 1, so the two are comparable. Per selected instrument, on
the post-2020 partition: **PASS** at PF > 1.2 and t > 2.0, **MARGINAL** at
PF > 1.1 and t > 1.5, **FAIL** otherwise.

### Expected outcome, stated in advance

The threshold selects **J7 alone**, on 890 pre-2020 trades. If that is what
happens, stage 2 is a single test with no multiplicity left to correct, and the
result is whatever J7 does post-2020. If the pre-2020 scan selects nothing at
all, that is a complete result and the README says so.

## Diagnostics — run after scoring, not before

None of these can change the selection or the verdict. They bound how much the
verdict is worth.

**Dependence.** `holdout_stage2.py bootstrap J7 --period post` resamples whole
calendar blocks from the demeaned trade series. The naive t assumes 570
independent draws. Post-2020 yen was one sustained depreciation, and a
trendline-walk rule fires repeatedly in the same direction inside it, so the
true count of independent bets is far lower. Report `inflation` and `n_eff`
alongside any t that gets published. **Registered in advance: if the year-block
inflation factor exceeds 2.0, the naive t is not reportable on its own and only
`t_adj` goes in the README.**

**Search size.** `holdout_stage2.py dsr J7 --period post` computes the deflated
Sharpe against the expected maximum across 131 trials, with the trial variance
read from the scan file rather than assumed. Registered in advance: DSR below
0.95 means the result is not separable from the best of a noisy search,
whatever the t says.

**Mechanism.** `holdout_stage2.py regime J7 --lookback 480` regresses trade
returns on direction-signed trailing trend with Newey-West errors. If the
intercept is not distinguishable from zero, the trendline construction adds
nothing over plain trend exposure and the honest description is "a trend
follower that happened to be pointed at the yen," not "a trendline edge."

## What the cross-instrument result already implies

Stage 1's Test 2 is the strongest evidence in the whole exercise and it points
the wrong way. RY came in at t +2.37 and PJY at −4.07, so the two yen crosses
disagree with each other. E6, B6 and A6 are all mildly negative. Under stage 1's
own criteria that is SUPPORTIVE on the letter of the rule, since RY clears
PF > 1.15, but a mechanism that produces +2.37 on one yen cross and −4.07 on
another is not a mechanism.

Stage 2 does not re-test this. It is recorded here so that a J7 pass in stage 2
is read in context: one instrument passing, with no corroboration from any
related instrument, is consistent with a single instrument having had a single
large trend.

## What gets published either way

Same rule as stage 1. The outcome goes in the README at the same prominence as
the existing tables, including the stage 1 correction above. If stage 2 fails,
the honest summary is: *a 131-instrument search produced four apparent
survivors; a contaminated holdout appeared to confirm two of them; a clean
holdout did not.*

---

**Committed:** `884416cfeda5eaba0e572c75cac2675b995ac592`, 2026-08-22 07:09:33 -0400.
This annotation was added in the following commit; the protocol content is
unchanged from the hash above, which is verifiable with
`git show 884416c:holdout_protocol_stage2.md`.

## Addendum, 22 Aug 2026 — trade data regenerated after registration

After this protocol was committed, a defect was found in backtest_hull.py:
entry and stop were stored as round(x, 4) and read back by the exit engine,
quantising the price grid to 100 ticks on instruments priced near 0.0068.
J7 and J1 were materially affected; J7 fell from +342.4R to +82.7R and J1
from +224.3R to +98.6R. PA and ZR were unaffected.

The selection procedure below is unchanged. The stated expectation that the
threshold would select J7 alone was derived from the defective data and is
expected to be wrong. That expectation is left in place rather than edited,
so the record shows what was predicted and what happened.

All stage 1 results, and the survivors table in the README, are computed on
the defective data and are withdrawn.
