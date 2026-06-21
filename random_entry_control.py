#!/usr/bin/env python3
"""Random-entry ("monkey") control for the trendline-walk strategy.

For each CSV it runs the real strategy, then runs a Monte-Carlo set of random
entries with the SAME trade count, the SAME exit engine, and the SAME stop
sizing (each symbol's median ATR stop distance). Only the entry bar and the
direction are randomized. It reports whether the strategy beats the random
distribution and by how many standard deviations, and can save a histogram.

This is the test of whether the edge lives in the entry selection or just in
the exits / market drift. On the metals the strategy sits ~5.8 sigma above the
random mean with zero random runs beating it.

Examples
--------
    python random_entry_control.py data/gold.csv --sims 500
    python random_entry_control.py data/GC.csv data/SI.csv data/HG.csv \
        --sims 500 --plot monkey.png
"""
import argparse, os
import numpy as np
from backtest_hull import run, load_series, ema, atr, exit_sim


def main():
    ap = argparse.ArgumentParser(description="random-entry control")
    ap.add_argument("paths", nargs="+", help="one or more OHLC csv files")
    ap.add_argument("--sims", type=int, default=500, help="Monte-Carlo iterations")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--plot", default=None, help="save a histogram PNG to this path")
    args = ap.parse_args()
    np.random.seed(args.seed)

    SD = {}
    strat_total = 0.0
    for p in args.paths:
        name = os.path.splitext(os.path.basename(p))[0]
        T, O, H, L, C = load_series(p)
        e21, e200, A = ema(C, 21), ema(C, 200), atr(H, L, C)
        start = int(T.min()) + 60 * 86400
        s, tr, _, _ = run(name, p, 1.0, start, CAP=1e12)
        if not tr:
            continue
        katr = float(np.median([abs(x["entry"] - x["stop0"]) / A[x["t0"]] for x in tr]))
        SD[name] = dict(O=O, H=H, L=L, C=C, e21=e21, e200=e200, A=A,
                        n=len(tr), katr=katr, si=int(np.searchsorted(T, start)))
        strat_total += s["totalR"]

    M = args.sims
    tot = np.zeros(M)
    for it in range(M):
        ssum = 0.0
        for d in SD.values():
            lo, hi = max(d["si"], 210), len(d["C"]) - 60
            bars = np.random.randint(lo, hi, size=d["n"])
            dirs = np.random.choice([-1, 1], size=d["n"])
            for t0, dd in zip(bars, dirs):
                entry = d["O"][t0]
                stop = entry - dd * d["katr"] * d["A"][t0]
                r = exit_sim(d["O"], d["H"], d["L"], d["C"], d["e21"], d["e200"],
                             d["A"], int(t0), float(entry), float(stop), int(dd))
                if r is not None:
                    ssum += r
        tot[it] = ssum

    z = (strat_total - tot.mean()) / tot.std()
    print(f"strategy total      : {strat_total:+.1f}R")
    print(f"random mean (n={M:<4d}): {tot.mean():+.1f}R   std {tot.std():.1f}   best {tot.max():+.1f}R")
    print(f"random 5th..95th    : {np.percentile(tot,5):+.1f}R .. {np.percentile(tot,95):+.1f}R")
    print(f"random runs beating : {100*(tot>=strat_total).mean():.1f}%")
    print(f"z vs random mean    : {z:.1f}")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
        ax.hist(tot, bins=40, color="#7d8da0", edgecolor="white")
        ax.axvline(tot.mean(), color="#e3a14a", ls="--", lw=2,
                   label=f"random mean {tot.mean():+.1f}R")
        ax.axvline(strat_total, color="#2e8b57", lw=3,
                   label=f"strategy {strat_total:+.1f}R")
        ax.set_xlabel("total R over the backtest")
        ax.set_ylabel("number of random simulations")
        ax.set_title(f"strategy vs {M} random-entry sims  (z = {z:.1f})")
        ax.legend()
        plt.tight_layout()
        plt.savefig(args.plot)
        print("saved", args.plot)


if __name__ == "__main__":
    main()
