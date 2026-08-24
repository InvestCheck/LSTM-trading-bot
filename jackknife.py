#!/usr/bin/env python3
"""Is the pooled edge broad, or carried by a few instruments?

A pooled t of +4.00 across 102 instruments says nothing about how the edge is
distributed. If five names carry it, the result is one concentrated bet wearing
a diversified costume, and it will not survive contact with a live book.

This is a robustness check, not a search. It cannot improve the result and adds
no multiplicity -- it can only reveal that what you already have is fragile.

Three views:
  leave-one-out   drop each instrument in turn, report the worst outcome
  drop-worst-k    drop the k BEST instruments and see what survives
  contribution    share of total net R coming from the top instruments

  python3 jackknife.py --min-ticks 20
  python3 jackknife.py --min-ticks 20 --boot 2000
"""
import argparse
import csv
import glob
import math
import os
from datetime import datetime, timezone

import numpy as np

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


def boot_t(x, times, B, seed=0):
    order = np.argsort(times)
    x = x[order]
    n = x.size
    t_obs = x.mean() / (x.std(ddof=1) / math.sqrt(n))
    if B <= 0:
        return t_obs, t_obs
    blocks = month_blocks(times[order])
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
    return t_obs, t_obs / sd_boot if sd_boot > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade-dir", default="backtests")
    ap.add_argument("--min-ticks", type=float, default=20.0)
    ap.add_argument("--max-cost-frac", type=float, default=0.10)
    ap.add_argument("--slip", type=float, default=1.0)
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()

    book = {}
    for p in sorted(glob.glob(os.path.join(a.trade_dir, "trades_*.csv"))):
        sym = os.path.basename(p)[7:-4]
        tick = TICKS.get(sym)
        if not tick:
            continue
        rows = list(csv.DictReader(open(p)))
        rpx = np.array([float(r["R_px"]) for r in rows], float)
        R = np.array([float(r["R_realized"]) for r in rows], float)
        ts = np.array([datetime.strptime(r["entry_time"], "%Y-%m-%d %H:%M")
                       .replace(tzinfo=timezone.utc).timestamp()
                       for r in rows], float)
        ok = rpx > 0
        if ok.sum() < 20:
            continue
        rpx, R, ts = rpx[ok], R[ok], ts[ok]
        tk = rpx / tick
        if 2.0 / float(np.median(tk)) > a.max_cost_frac:
            continue
        keep = tk >= a.min_ticks
        if keep.sum() < 20:
            continue
        book[sym] = (R[keep] - 2.0 * a.slip / tk[keep], ts[keep])

    syms = sorted(book)
    if len(syms) < 10:
        raise SystemExit(f"only {len(syms)} instruments; nothing to jackknife")

    allx = np.concatenate([book[s][0] for s in syms])
    allt = np.concatenate([book[s][1] for s in syms])
    t0, adj0 = boot_t(allx, allt, a.boot)
    print(f"{len(syms)} instruments, {allx.size} trades, net avgR "
          f"{allx.mean():+.4f}, total {allx.sum():+.1f}")
    print(f"full book: naive t {t0:+.2f}, t_adj {adj0:+.2f}\n")

    tot = allx.sum()
    contrib = sorted(((book[s][0].sum(), s) for s in syms), reverse=True)
    print("top contributors by net R")
    print(f"{'':4s} {'symbol':7s} {'net R':>8s} {'share':>7s} {'cumulative':>11s}")
    c = 0.0
    for i, (v, s) in enumerate(contrib[:10], 1):
        c += v
        print(f"{i:3d}. {s:7s} {v:+8.1f} {v/tot:7.1%} {c/tot:11.1%}")
    neg = sum(1 for v, _ in contrib if v < 0)
    print(f"\n{len(syms)-neg} of {len(syms)} instruments positive, {neg} negative")

    print("\ndrop the k BEST instruments:")
    print(f"{'k':>3s} {'kept':>5s} {'trades':>7s} {'net avgR':>9s} "
          f"{'net total':>10s} {'t_adj':>7s}")
    print("-" * 46)
    for k in (0, 1, 3, 5, 10, 20):
        if k >= len(syms) - 5:
            break
        drop = {s for _, s in contrib[:k]}
        keep = [s for s in syms if s not in drop]
        x = np.concatenate([book[s][0] for s in keep])
        tt = np.concatenate([book[s][1] for s in keep])
        _, adj = boot_t(x, tt, a.boot)
        print(f"{k:3d} {len(keep):5d} {x.size:7d} {x.mean():+9.4f} "
              f"{x.sum():+10.1f} {adj:+7.2f}")
    print("-" * 46)

    print("\nleave-one-out, worst five:")
    loo = []
    for s in syms:
        keep = [q for q in syms if q != s]
        x = np.concatenate([book[q][0] for q in keep])
        tt = np.concatenate([book[q][1] for q in keep])
        _, adj = boot_t(x, tt, min(a.boot, 400))
        loo.append((adj, s))
    loo.sort()
    for adj, s in loo[:5]:
        print(f"  without {s:7s} t_adj {adj:+.2f}")
    print(f"  best case  {loo[-1][1]:7s} t_adj {loo[-1][0]:+.2f}")

    print("\nIf t_adj holds up after dropping the top 5, the edge is broad and\n"
          "the pooled figure means what it appears to mean. If it collapses,\n"
          "the result is a few instruments and should be described that way.")


if __name__ == "__main__":
    main()
