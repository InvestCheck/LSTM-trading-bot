#!/usr/bin/env python3
"""Does stop width predict gross edge? If not, a trade-level cost filter is free.

Cost per trade is 2*tick/R, so a trade with a 25-tick stop pays 8% of the bet
while one with a 128-tick stop pays 1.6%. Excluding the narrow ones is
arithmetic, not a fitted pattern -- the same mechanical argument that excluded
ZQ at the instrument level, applied one level down.

The saving is only real if gross avgR does not fall with stop width. If wide
stops systematically produce worse outcomes in R terms, the cost saving is
cancelled by lost edge and the filter does nothing. This buckets trades by
stop width and reports gross and net avgR in each bucket so the two effects can
be seen separately.

This is NOT a fitted filter. It reports what the arithmetic already implies and
checks the one assumption behind it. Choosing the bucket that maximises net R
and calling it a strategy WOULD be fitting -- the threshold has to be argued
from execution, not from the totals it produces.

  python3 stop_width.py                     # all instruments, default buckets
  python3 stop_width.py --min-cost-frac 0.10  # match span_sweep's universe
"""
import argparse
import csv
import glob
import os

import numpy as np

from instruments import TICKS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-dir", default="backtests")
    ap.add_argument("--buckets", nargs="+", type=float,
                    default=[0, 20, 32, 48, 64, 96, 128, 1e9])
    ap.add_argument("--max-cost-frac", type=float, default=0.10,
                    help="drop instruments whose MEDIAN bet is this costly; "
                         "matches the universe used in span_sweep")
    a = ap.parse_args()

    ticks, R = [], []
    for p in sorted(glob.glob(os.path.join(a.trade_dir, "trades_*.csv"))):
        sym = os.path.basename(p)[7:-4]
        tick = TICKS.get(sym)
        if not tick:
            continue
        rows = list(csv.DictReader(open(p)))
        rpx = np.array([float(r["R_px"]) for r in rows], float)
        rr = np.array([float(r["R_realized"]) for r in rows], float)
        ok = rpx > 0
        if ok.sum() < 20:
            continue
        t = rpx[ok] / tick
        if 2.0 / float(np.median(t)) > a.max_cost_frac:
            continue                      # unexecutable instrument, excluded
        ticks.append(t)
        R.append(rr[ok])

    if not ticks:
        raise SystemExit("no eligible trade files found")
    t = np.concatenate(ticks)
    R = np.concatenate(R)
    cost = 2.0 / t                        # exact: engine charges 2*tick/R
    net = R - cost

    print(f"{t.size} trades, median stop {np.median(t):.0f} ticks\n")
    hdr = (f"{'stop (ticks)':>14s} {'trades':>7s} {'share':>6s} {'cost/bet':>9s} "
           f"{'gross avgR':>11s} {'net avgR':>9s} {'net t':>7s}")
    print(hdr); print("-" * len(hdr))
    for lo, hi in zip(a.buckets, a.buckets[1:]):
        m = (t >= lo) & (t < hi)
        if m.sum() < 30:
            continue
        g, n = R[m], net[m]
        tt = n.mean() / (n.std(ddof=1) / np.sqrt(n.size))
        label = f"{lo:.0f}-{hi:.0f}" if hi < 1e8 else f"{lo:.0f}+"
        print(f"{label:>14s} {m.sum():7d} {m.mean():6.1%} {cost[m].mean():9.1%} "
              f"{g.mean():+11.4f} {n.mean():+9.4f} {tt:+7.2f}")
    print("-" * len(hdr))

    # cumulative view: what a floor at each threshold would leave
    print(f"\n{'floor':>8s} {'kept':>7s} {'share':>6s} {'gross avgR':>11s} "
          f"{'net avgR':>9s} {'net total':>10s} {'net t':>7s}")
    print("-" * 62)
    for lo in a.buckets[:-1]:
        m = t >= lo
        if m.sum() < 100:
            continue
        n = net[m]
        tt = n.mean() / (n.std(ddof=1) / np.sqrt(n.size))
        print(f"{lo:8.0f} {m.sum():7d} {m.mean():6.1%} {R[m].mean():+11.4f} "
              f"{n.mean():+9.4f} {n.sum():+10.1f} {tt:+7.2f}")
    print("-" * 62)
    print("Read the GROSS column first. If it is flat across buckets, stop width\n"
          "carries no edge information and the cost saving is real. If it falls as\n"
          "stops widen, the filter is trading edge for cost and may net to nothing.\n"
          "net t here is the naive iid figure; run the cluster bootstrap before\n"
          "believing any of it.")


if __name__ == "__main__":
    main()
