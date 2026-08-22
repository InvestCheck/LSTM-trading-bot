#!/usr/bin/env python3
"""Span sweep: does a longer trendline give a bigger bet?

The economics of this strategy come down to one ratio. Cost per trade is
2 * tick / R, so the only lever that changes the answer is R itself. Total R is
the wrong number to read here, because a config can lose more in aggregate
simply by taking more trades while each individual bet gets cheaper to hold.

This runs each span config once at ZERO slippage and derives the costed result
analytically, which is exact: backtest_hull charges rr -= 2*slip*tick/R, and
R_px in the trade file is that same R. One pass gives gross and net at every
slippage level.

Reported per config:
  trades        how many signals the span window admits
  gross R       total before costs
  gross avgR    the edge per bet, the thing that must survive
  med ticks     median stop distance in ticks, pooled across instruments
  cost/bet      2 ticks / R as a fraction, at 1 tick per side
  net @0.5/1    total R after costs, derived not re-simulated

Usage:
  python3 span_sweep.py --data-dir DIR
  python3 span_sweep.py --data-dir DIR --configs 168:1200 2160:17520 168:99999999
  python3 span_sweep.py --data-dir DIR --symbols GC PL HG PA ZR   # quick look

REGISTER THE CONFIG LIST BEFORE RUNNING. Each config is a test. If one looks
good out of four, the correction is for four.
"""
import argparse
import os
import math
import statistics as st
import sys

import numpy as np

from backtest_hull import run, load_series
from batch_backtest import build_catalog
from instruments import TICKS


def parse_cfg(s):
    try:
        lo, hi = s.split(":")
        lo, hi = int(lo), int(hi)
    except ValueError:
        sys.exit(f"bad config {s!r}, want MINSPAN:MAXSPAN e.g. 2160:17520")
    if lo >= hi:
        sys.exit(f"bad config {s!r}, minspan must be below maxspan")
    return lo, hi


def _blocks_by(times, freq):
    from datetime import datetime, timezone
    keys = []
    for t in times:
        dt = datetime.fromtimestamp(int(t), timezone.utc)
        keys.append((dt.year, dt.month) if freq == "month" else
                    (dt.year, (dt.month - 1) // 3) if freq == "quarter" else (dt.year,))
    blocks, cur, prev = [], [], None
    for i, k in enumerate(keys):
        if prev is not None and k != prev:
            blocks.append(np.array(cur)); cur = []
        cur.append(i); prev = k
    blocks.append(np.array(cur))
    return blocks


def _boot_t(R, blocks, B, seed=0):
    n = R.size
    t_obs = R.mean() / (R.std(ddof=1) / math.sqrt(n))
    xc = R - R.mean()
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
    return t_obs, sd_boot, float(np.mean(np.abs(ts) >= abs(t_obs)))


def _cluster_boot(times, R, B, n_inst, ticks=None, seed=0):
    """Calendar-block bootstrap over the pooled cross-section.

    The naive pooled t treats every trade as an independent draw. It is not: the
    strategy holds correlated positions simultaneously across many instruments,
    so a month in which metals trended is one event expressed dozens of times.
    Resampling whole months across ALL instruments together keeps those
    simultaneous trades bound to each other, which is the dependence the naive
    statistic ignores.
    """
    order = np.argsort(times)
    R, times = R[order], times[order]
    net = R - 2.0 / ticks[order] if ticks is not None else None

    print(f"{'':>18s} pooled cluster bootstrap, {n_inst} instruments, {B} resamples")
    print(f"{'':>18s} {'blocks':>8s} {'count':>6s} {'series':>7s} "
          f"{'naive t':>8s} {'infl':>6s} {'t_adj':>7s} {'p':>8s}")
    for freq in ("month", "quarter", "year"):
        blocks = _blocks_by(times, freq)
        for label, x in (("gross", R), ("net@1", net)):
            if x is None:
                continue
            t_obs, sd, p = _boot_t(x, blocks, B, seed)
            print(f"{'':>18s} {freq:>8s} {len(blocks):6d} {label:>7s} "
                  f"{t_obs:+8.2f} {sd:6.2f} {t_obs/sd:+7.2f} {p:8.4f}")
    print(f"{'':>18s} net@1 is the tradeable series: gross R minus 2 ticks per trade.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="seed")
    ap.add_argument("--configs", nargs="+",
                    default=["168:1200", "720:4320", "2160:17520", "168:99999999"])
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--warmup-days", type=int, default=60)
    ap.add_argument("--cluster-boot", type=int, default=0, metavar="B",
                    help="B resamples of a calendar-block bootstrap over the POOLED "
                         "trade set. Resamples whole months across all instruments "
                         "together, so simultaneous correlated positions move as one "
                         "draw. The pooled naive t assumes every trade is independent "
                         "and is badly overstated; this is the honest version.")
    ap.add_argument("--split-at", default=None,
                    help="YYYY-MM-DD; report each config split into pre and post. "
                         "Not a holdout: this data has already been used. It only "
                         "shows whether the effect is stable in time.")
    ap.add_argument("--max-cost-frac", type=float, default=0.10,
                    help="exclude instruments where 1 tick round trip exceeds this "
                         "share of the median bet; they are unexecutable, not unprofitable")
    a = ap.parse_args()

    catalog = build_catalog(a.data_dir)
    if not catalog:
        sys.exit(f"no price files in {a.data_dir}/")
    syms = [s for s in (a.symbols or sorted(catalog)) if s in catalog]
    cfgs = [parse_cfg(c) for c in a.configs]

    print(f"{len(syms)} symbols, {len(cfgs)} span configs, zero-slippage pass\n")
    hdr = (f"{'span':>18s} {'trades':>7s} {'gross R':>9s} {'gross avgR':>11s} "
           f"{'med ticks':>10s} {'cost/bet':>9s} {'net @0.5':>9s} {'net @1':>9s}")
    print(hdr)
    print("-" * len(hdr))

    cut = None
    if a.split_at:
        from datetime import datetime, timezone
        cut = datetime.strptime(a.split_at, "%Y-%m-%d").replace(
            tzinfo=timezone.utc).timestamp()

    for lo, hi in cfgs:
        allR, allticks, kept = [], [], 0
        preR, postR = [], []
        allT = []
        for s in syms:
            tick = TICKS.get(s)
            if not tick:
                continue
            path = catalog[s]
            T, *_ = load_series(path)
            start = int(T.min()) + a.warmup_days * 86400
            try:
                _, trades, _, _ = run(s, path, 1.0, start, CAP=1e12,
                                      MAXSPAN=hi, MINSPAN=lo, tick=0.0,
                                      slip_ticks=0.0, fill="intrabar", causal=True)
            except Exception as e:
                print(f"  {s}: {e}", file=sys.stderr)
                continue
            R = np.array([t["R"] for t in trades], float)
            rpx = np.array([abs(t["entry"] - t["stop0"]) for t in trades], float)
            ok = rpx > 0
            if ok.sum() < 20:
                continue
            R, rpx = R[ok], rpx[ok]
            if 2 * tick / float(np.median(rpx)) > a.max_cost_frac:
                continue          # unexecutable at any span, not a span question
            allR.append(R)
            allticks.append(rpx / tick)
            ts = np.array([T[t["t0"]] for t in trades], float)[ok]
            allT.append(ts)
            if cut is not None:
                preR.append(R[ts < cut]); postR.append(R[ts >= cut])
            kept += 1

        if not allR:
            print(f"{lo:>8d}..{hi:<8d}  (no eligible instruments)")
            continue
        R = np.concatenate(allR)
        ticks = np.concatenate(allticks)
        med = float(np.median(ticks))
        gross = float(R.sum())
        # exact cost: 2 * slip * tick / R, and ticks already = R / tick
        cost_half = float((2 * 0.5 / ticks).sum())
        cost_one = float((2 * 1.0 / ticks).sum())
        print(f"{lo:>8d}..{hi:<8d} {R.size:7d} {gross:+9.1f} {R.mean():+11.4f} "
              f"{med:10.1f} {2.0/med:9.1%} {gross-cost_half:+9.1f} {gross-cost_one:+9.1f}")
        if a.cluster_boot:
            _cluster_boot(np.concatenate(allT), R, a.cluster_boot, kept, ticks=ticks)
        if cut is not None:
            for label, part in (("  pre", preR), (" post", postR)):
                x = np.concatenate(part)
                if x.size < 20:
                    continue
                t = x.mean() / (x.std(ddof=1) / np.sqrt(x.size))
                print(f"{label:>18s} {x.size:7d} {x.sum():+9.1f} {x.mean():+11.4f} "
                      f"{'':10s} {'':9s}   pooled t {t:+.2f}")

    print("-" * len(hdr))
    print(f"instruments where 1 tick exceeds {a.max_cost_frac:.0%} of the median bet are\n"
          f"excluded throughout; no span setting makes those executable.\n"
          f"The number that matters is 'gross avgR' holding up while 'cost/bet' falls.\n"
          f"A config that raises total R by taking more trades has not helped.")


if __name__ == "__main__":
    main()
