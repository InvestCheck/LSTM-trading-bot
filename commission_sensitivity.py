#!/usr/bin/env python3
"""How bad would the unverified contracts have to be to kill the result?

commissions.py covers 40 of the ~103 executable contracts. Filling in the rest
means reading a contract specification page per symbol. Before doing that work,
it is worth knowing whether the answer could plausibly change -- and that can be
established WITHOUT guessing a single tick value.

Method: apply exact commissions to the verified symbols, and sweep an assumed
commission rate across the unverified ones. If the pooled result survives even
a pessimistic assumption, the verification is confirmatory and can wait. If it
dies at a moderate assumption, verification is the critical path.

The assumed rate is expressed as a share of the bet at the median stop width,
then scaled per trade by 1/ticks, which is how commission actually behaves: a
wider stop is a larger bet and the same dollar commission is a smaller share.

Reference points from the 40 verified contracts at a 78-tick bet:
    median 0.61%   mean 1.02%   worst 3.18% (the micros: MNQ, M2K, MBT, MET)

  python3 commission_sensitivity.py --min-ticks 20
  python3 commission_sensitivity.py --min-ticks 20 --boot 5000
"""
import argparse
import csv
import glob
import math
import os
from datetime import datetime, timezone

import numpy as np

from commissions import TICK_VALUE, cost_in_R
from instruments import TICKS


def month_blocks(times):
    keys = [(datetime.fromtimestamp(int(t), timezone.utc).year,
             datetime.fromtimestamp(int(t), timezone.utc).month) for t in times]
    blocks, cur, prev = [], [], None
    for i, k in enumerate(keys):
        if prev is not None and k != prev:
            blocks.append(np.array(cur)); cur = []
        cur.append(i); prev = k
    blocks.append(np.array(cur))
    return blocks


def boot_t(x, blocks, B, seed=0):
    n = x.size
    t_obs = x.mean() / (x.std(ddof=1) / math.sqrt(n))
    if B <= 0:
        return t_obs, 1.0, t_obs
    xc = x - x.mean()
    rng = np.random.default_rng(seed)
    nb = len(blocks)
    draw = int(math.ceil(n / max(1.0, n / nb))) + 2
    ts = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, nb, size=draw)
        y = np.concatenate([xc[blocks[j]] for j in pick])[:n]
        sd = y.std(ddof=1)
        ts[b] = y.mean() / (sd / math.sqrt(y.size)) if sd > 0 else 0.0
    sd_boot = float(ts.std(ddof=1))
    return t_obs, sd_boot, t_obs / sd_boot if sd_boot > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-dir", default="backtests")
    ap.add_argument("--min-ticks", type=float, default=20.0)
    ap.add_argument("--max-cost-frac", type=float, default=0.10)
    ap.add_argument("--slip", type=float, default=1.0)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    ver_R, ver_t, ver_c, ver_ts = [], [], [], []
    unv_R, unv_t, unv_ts, unv_syms = [], [], [], []

    for p in sorted(glob.glob(os.path.join(a.trade_dir, "trades_*.csv"))):
        sym = os.path.basename(p)[7:-4]
        tick = TICKS.get(sym)
        if not tick:
            continue
        rows = list(csv.DictReader(open(p)))
        rpx = np.array([float(r["R_px"]) for r in rows], float)
        R = np.array([float(r["R_realized"]) for r in rows], float)
        ts = np.array([datetime.strptime(r["entry_time"], "%Y-%m-%d %H:%M")
                       .replace(tzinfo=timezone.utc).timestamp() for r in rows], float)
        ok = rpx > 0
        if ok.sum() < 20:
            continue
        rpx, R, ts = rpx[ok], R[ok], ts[ok]
        tks = rpx / tick
        if 2.0 / float(np.median(tks)) > a.max_cost_frac:
            continue
        keep = tks >= a.min_ticks
        if keep.sum() < 20:
            continue
        R, tks, ts = R[keep], tks[keep], ts[keep]
        if sym in TICK_VALUE:
            ver_R.append(R); ver_t.append(tks); ver_ts.append(ts)
            ver_c.append(np.array([cost_in_R(sym, x) for x in tks]))
        else:
            unv_R.append(R); unv_t.append(tks); unv_ts.append(ts)
            unv_syms.append(sym)

    vR = np.concatenate(ver_R) if ver_R else np.array([])
    uR = np.concatenate(unv_R) if unv_R else np.array([])
    vT = np.concatenate(ver_t) if ver_t else np.array([])
    uT = np.concatenate(unv_t) if unv_t else np.array([])
    vC = np.concatenate(ver_c) if ver_c else np.array([])
    times = np.concatenate((np.concatenate(ver_ts) if ver_ts else np.array([]),
                            np.concatenate(unv_ts) if unv_ts else np.array([])))
    n_tot = vR.size + uR.size
    med = float(np.median(np.concatenate((vT, uT))))

    print(f"trade floor {a.min_ticks:.0f} ticks, {n_tot} trades, "
          f"median stop {med:.0f} ticks\n")
    print(f"  verified tick value    {len(ver_R):3d} symbols  {vR.size:6d} trades "
          f"({vR.size/n_tot:5.1%})")
    print(f"  UNVERIFIED             {len(unv_R):3d} symbols  {uR.size:6d} trades "
          f"({uR.size/n_tot:5.1%})")
    if unv_syms:
        print(f"    {' '.join(sorted(unv_syms))}")

    # slippage-only net, both groups
    net_slip = np.concatenate((vR - 2.0 * a.slip / vT, uR - 2.0 * a.slip / uT))
    order = np.argsort(times)
    blocks = month_blocks(times[order])

    print(f"\nslippage only: net avgR {net_slip.mean():+.4f}")
    t0, inf0, adj0 = boot_t(net_slip[order], blocks, a.boot)
    print(f"  naive t {t0:+.2f}  inflation {inf0:.2f}  t_adj {adj0:+.2f}\n")

    hdr = (f"{'assumed cost on unverified':>28s} {'net avgR':>9s} {'net total':>10s} "
           f"{'naive t':>8s} {'t_adj':>7s}")
    print(hdr); print("-" * len(hdr))
    scenarios = [(0.0061, "verified median 0.61%"),
                 (0.0102, "verified mean 1.02%"),
                 (0.0200, "2.00%"),
                 (0.0318, "verified worst 3.18%"),
                 (0.0500, "5.00%"),
                 (0.0800, "8.00%")]
    for rate, label in scenarios:
        # rate is the share at the median stop; scales as 1/ticks per trade
        # scale by 1/ticks, but cap: a commission above half the bet means the
        # contract is unexecutable, not merely expensive
        uc = np.minimum(rate * med / uT, 0.5)
        net = np.concatenate((vR - 2.0 * a.slip / vT - vC,
                              uR - 2.0 * a.slip / uT - uc))[order]
        t, inf, adj = boot_t(net, blocks, a.boot)
        print(f"{label:>28s} {net.mean():+9.4f} {net.sum():+10.1f} "
              f"{t:+8.2f} {adj:+7.2f}")
    print("-" * len(hdr))

    # what rate on the unverified drives the pooled net to zero
    base = (vR - 2.0 * a.slip / vT - vC).sum()
    slip_u = (uR - 2.0 * a.slip / uT).sum()
    denom = float((med / uT).sum())
    if denom > 0:
        be = (base + slip_u) / denom
        be = max(0.0, be)
        print(f"\nBREAKEVEN: the unverified contracts would need to cost "
              f"{be:.2%} of the bet\n(at the median stop) to drive the pooled "
              f"result to zero.")
        print(f"The worst verified contract costs 3.18%. Read that against the "
              f"breakeven\nto decide whether filling in the specs is confirmatory "
              f"or critical path.")


if __name__ == "__main__":
    main()
