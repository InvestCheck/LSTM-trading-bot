#!/usr/bin/env python3
"""How much does a RANDOM filter improve results? The monkey control for filters.

Same logic as random_entry_control.py, one level up. That script asks whether
the entry signal beats random entries. This asks whether a filter beats random
filters.

Any filter fitted on this data will improve the numbers, because the data has
already been used for instrument selection, contamination analysis, the span
sweep and four rounds of defect hunting. The question is not whether an
improvement appears -- it always does -- but whether it is larger than what
random search produces on the same trades.

Method: generate B random filters over the signal-time columns only (never an
outcome column), keep those retaining at least --min-keep of the trades, and
report the distribution of net avgR they produce. The best of B is the number
that matters: a fitted filter is a best-of-many search, so it must be compared
against the best of many random searches, not against the unfiltered baseline.

  python3 filter_control.py PA
  python3 filter_control.py PA --sims 2000 --min-keep 0.3
  python3 filter_control.py PA --my-filter "touches>=4,span_bars>=3000"

If your filter's net avgR sits inside the random distribution, it is noise, and
no amount of refinement on this data will tell you otherwise. If it sits well
outside, that is necessary but not sufficient -- it still needs forward
validation, because this test cannot rule out that you found the same lucky
pattern the random search would have found with more draws.
"""
import argparse
import csv
import math
import os
from datetime import datetime, timezone

import numpy as np

from instruments import TICKS

# Signal-time columns only. Never add an outcome column here; the repo's
# leakage rule exists because the tier model has been burned by this before.
NUMERIC = ["R_px", "touches", "span_bars", "slope", "dir"]
CATEGORICAL = ["kind", "stop_src"]


def load(sym, trade_dir="backtests"):
    path = os.path.join(trade_dir, f"trades_{sym}.csv")
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"no trades in {path}")
    feats, R = {}, []
    hours = []
    for c in NUMERIC:
        feats[c] = []
    for c in CATEGORICAL:
        feats[c] = []
    for r in rows:
        for c in NUMERIC:
            feats[c].append(float(r[c]))
        for c in CATEGORICAL:
            feats[c].append(r[c])
        R.append(float(r["R_realized"]))
        hours.append(datetime.strptime(r["entry_time"], "%Y-%m-%d %H:%M")
                     .replace(tzinfo=timezone.utc).hour)
    feats["hour"] = [float(h) for h in hours]
    num = {c: np.array(feats[c], float) for c in NUMERIC + ["hour"]}
    cat = {c: np.array(feats[c], object) for c in CATEGORICAL}
    return num, cat, np.array(R, float)


def net_series(R, rpx, tick):
    """Exact net R: the engine charges 2*slip*tick/R and R_px is that R."""
    if not tick:
        return R
    return R - 2.0 / (rpx / tick)


def random_mask(num, cat, rng, max_clauses=3):
    """A random conjunction of threshold clauses over signal-time features."""
    keys = list(num) + list(cat)
    k = rng.integers(1, max_clauses + 1)
    mask = np.ones(len(next(iter(num.values()))), bool)
    for _ in range(k):
        key = keys[rng.integers(0, len(keys))]
        if key in num:
            v = num[key]
            lo, hi = np.percentile(v, [5, 95])
            thr = rng.uniform(lo, hi)
            mask &= (v >= thr) if rng.random() < 0.5 else (v <= thr)
        else:
            v = cat[key]
            vals = np.unique(v)
            if vals.size < 2:
                continue
            pick = vals[rng.integers(0, vals.size)]
            mask &= (v == pick) if rng.random() < 0.5 else (v != pick)
    return mask


def parse_my_filter(spec, num, cat):
    mask = np.ones(len(next(iter(num.values()))), bool)
    for clause in spec.split(","):
        clause = clause.strip()
        for op in (">=", "<=", "==", "!="):
            if op in clause:
                key, val = clause.split(op, 1)
                key, val = key.strip(), val.strip()
                if key in num:
                    x, v = num[key], float(val)
                    mask &= {">=": x >= v, "<=": x <= v,
                             "==": x == v, "!=": x != v}[op]
                elif key in cat:
                    x = cat[key]
                    mask &= (x == val) if op in ("==", ">=") else (x != val)
                else:
                    raise SystemExit(f"unknown feature {key!r}")
                break
        else:
            raise SystemExit(f"cannot parse clause {clause!r}")
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--trade-dir", default="backtests")
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--min-keep", type=float, default=0.25,
                    help="reject filters retaining less than this share; below "
                         "it you are cherry-picking individual trades")
    ap.add_argument("--slip", type=float, default=1.0)
    ap.add_argument("--my-filter", default=None,
                    help='e.g. "touches>=4,span_bars>=3000"')
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    num, cat, R = load(a.symbol, a.trade_dir)
    tick = TICKS.get(a.symbol)
    net = net_series(R, num["R_px"], tick * a.slip if tick else 0.0)
    base = net.mean()
    print(f"{a.symbol}: {R.size} trades, unfiltered net avgR {base:+.4f}, "
          f"total {net.sum():+.1f}\n")

    rng = np.random.default_rng(a.seed)
    out = []
    tries = 0
    while len(out) < a.sims and tries < a.sims * 20:
        tries += 1
        m = random_mask(num, cat, rng)
        if m.mean() < a.min_keep or m.sum() < 30:
            continue
        out.append(net[m].mean())
    if len(out) < 50:
        raise SystemExit("too few valid random filters; lower --min-keep")
    arr = np.array(out)

    print(f"{len(arr)} random filters retaining >= {a.min_keep:.0%} of trades")
    print(f"  mean net avgR      {arr.mean():+.4f}")
    print(f"  5th..95th          {np.percentile(arr,5):+.4f} .. "
          f"{np.percentile(arr,95):+.4f}")
    print(f"  BEST of {len(arr):<5d}      {arr.max():+.4f}   "
          f"(+{arr.max()-base:.4f} over unfiltered)")
    print(f"\nA random filter improves net avgR by {arr.max()-base:+.4f} on this "
          f"symbol\nwith no information whatsoever. That is the bar.")

    if a.my_filter:
        m = parse_my_filter(a.my_filter, num, cat)
        n_keep = int(m.sum())
        if n_keep < 2:
            raise SystemExit(f"\nyour filter: {a.my_filter}\n  keeps "
                             f"{n_keep} trades of {R.size}. Nothing to test.")
        mine, keep = net[m].mean(), m.mean()
        print(f"\nyour filter: {a.my_filter}")
        print(f"  keeps {keep:.0%} of trades ({n_keep} of {R.size})")
        print(f"  net avgR {mine:+.4f}  (+{mine-base:.4f} over unfiltered)")

        # A null built at a different retention rate is the WRONG null. Filters
        # keeping fewer trades have far higher variance and a far higher
        # best-of-N, so comparing across retention rates flatters tight filters.
        # Rebuild the null matched to this filter's own retention.
        lo, hi = keep * 0.7, keep * 1.4
        matched, tries = [], 0
        while len(matched) < a.sims and tries < a.sims * 60:
            tries += 1
            mm = random_mask(num, cat, rng)
            if lo <= mm.mean() <= hi and mm.sum() >= 5:
                matched.append(net[mm].mean())
        se = net[m].std(ddof=1) / math.sqrt(max(1, n_keep))
        print(f"  standard error on {n_keep} trades: {se:.4f}  "
              f"({(mine-base)/se:+.1f} SE above unfiltered)")

        if len(matched) < 50:
            print(f"\n  Could not build a matched null at {keep:.0%} retention "
                  f"({len(matched)} draws).\n  Treat the comparison above as "
                  f"unsupported.")
        else:
            marr = np.array(matched)
            pct = float((marr >= mine).mean())
            print(f"\n  matched null: {len(marr)} random filters keeping "
                  f"{lo:.0%}-{hi:.0%} of trades")
            print(f"    mean {marr.mean():+.4f}   best {marr.max():+.4f}")
            print(f"    {pct:.1%} of them did as well or better")
            if n_keep < 30:
                print(f"\n  {n_keep} trades is too few to conclude anything "
                      f"either way, regardless\n  of where it lands in the "
                      f"null. A mean over {n_keep} trades has a standard\n  "
                      f"error of {se:.2f}R.")
            elif pct > 0.05:
                print("\n  Inside the matched random distribution. Not evidence "
                      "of anything.")
            else:
                print("\n  Outside the matched random distribution. Necessary, "
                      "not sufficient:\n  it still needs forward validation, "
                      "since this cannot rule out that you\n  found the pattern "
                      "a larger random search would also find.")


if __name__ == "__main__":
    main()
