# Results directory

Datestamped output. Read this before citing anything in here — some of it is
withdrawn and kept only so the correction is auditable.

---

## WITHDRAWN — stage 1 holdout, 22 Aug 2026

```
holdout_timesplit_20260822_0947.csv
holdout_crossinstrument_20260822_0947.csv
holdout_power_20260822_0947.csv
```

**Do not cite these files.** They report PASS for J7 and J1, MARGINAL for PA and
ZR. Every one of those verdicts is void, for two independent reasons.

**The data was defective.** These trades were generated before a price rounding
defect in `backtest_hull.py` was found (bias source 4 in the main README). J7 and
J1 — the two instruments reported as PASS — are exactly the two the defect
corrupted. J7 fell from +342.4R to +82.7R once fixed, so its headline was 76%
artifact.

**The selection was contaminated.** The four instruments were chosen on
*full-sample* t, and the full sample contains the post-2020 holdout. The share of
the selection statistic that is literally the holdout is `sqrt(n_post / n_full)`:
0.62 for J7, 0.61 for J1.

Two specific numbers in these files are worth flagging because they were quoted
elsewhere before being corrected:

- **PJY at t −4.07** in the cross-instrument file reads as evidence against a JPY
  mechanism. It is mostly a cost artifact: PJY's median stop is 7.8 ticks, so one
  tick round trip is 25.7% of the bet. Gross, PJY is *positive*.
- **PA and ZR are uninformative, not marginal.** Projecting the in-sample effect
  onto the realised holdout counts gives an expected t of 2.11 for PA and 1.46
  for ZR. ZR delivered 1.65, slightly *above* what a fully real edge would
  produce at n = 63. It demonstrated nothing because at that sample size it could
  not have, either way.

Superseded by `holdout_protocol_stage2.md`, which ran the selection on pre-cutoff
data first and froze the list before scoring. It selected nothing.

---

## PARTIALLY UNRELIABLE — notebook scan output

```
scan_results_long_20260810_1741.csv
scan_summary_20260810_1741.csv
```

Produced 10 Aug 2026, before the rounding fix. Rows for low-priced instruments —
J7, J1, and any other contract where four decimal places are coarse relative to
the tick — are unreliable. Rows for normally-priced contracts (PA, ZR, GC, PL and
similar) are unaffected and reproduce exactly on the corrected build.

The portfolio totals in `scan_summary` predate the fix: the costed figure moved
from −3,062.1R to −3,564.2R once corrected.

Still used as a live input by `holdout_stage2.py dsr`, which reads only the
`trades` and `tstat` columns to estimate the cross-trial Sharpe variance. That
use is unaffected, since it depends on the distribution across instruments rather
than on any individual row.

---

## Current

```
selection_pre2020-01-01.json
```

The stage 2 frozen selection. **Empty by design** — no instrument cleared
t > 3.55 on pre-2020 data. Contains the ranking of all 131 instruments on the
pre-cutoff period, the threshold and criteria fixed at freeze time, and a sha256
of every trade file so `score` can detect if the backtest was re-run underneath
it.

Committed before `score` was run. That ordering is the entire point of the file.

```
batch_fixed_20260822_0728.log
batch_fixed_20260822_0735.log
```

Full scan output on the corrected build, 131 instruments at 1 tick per side.
The two runs are identical; either is canonical. **These are the current
numbers** (70,187 trades, −3,564.2R).

```
batch_20260822_0711.log
batch_20260822_0713.log
batch_20260822_0714.log
```

Superseded. Same day, but **before** the rounding fix landed at roughly 07:20.
These report the −3,062.1R total and J7 at +342.4R. Kept as the record of what
the defect looked like; do not cite them for current performance. The
distinguishing feature is the filename: `batch_fixed_*` is post-fix,
`batch_*` is not.

## Regenerating the trade files

`backtests/trades_<SYM>.csv` is derived data and is not tracked. The sha256
hashes frozen in `selection_pre2020-01-01.json` correspond to a 1 tick per side
run on the corrected build:

```bash
python3 batch_backtest.py --data-dir DATA_DIR --slip 1
```

Any other `--slip` value produces different `R_realized` values and different
hashes, which `holdout_stage2.py score` will flag. Price data is FirstRateData
and is not redistributed here.

---

## Conventions

- Filenames carry a `YYYYMMDD_HHMM` UTC stamp.
- Nothing in here is deleted. Superseded output gets a withdrawal note in this
  file instead, so the correction history stays inspectable.
- The price rounding fix landed 22 Aug 2026 at roughly 07:20 UTC. Anything
  produced before that point is suspect for low-priced instruments (J7, J1 and
  similar). Check the filename convention above before citing a log.
