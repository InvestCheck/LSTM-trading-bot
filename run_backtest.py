#!/usr/bin/env python3
"""Run the trendline-walk backtest on one or more OHLC CSV files.

Defaults are the HONEST settings: fill='intrabar', causal=True.

Examples
--------
    python run_backtest.py data/gold.csv
    python run_backtest.py data/GC.csv --start 2008-03-01 --name Gold
    python run_backtest.py data/GC.csv --legacy       # old inflated numbers

Fill models (--fill):
    intrabar  (default) resting-stop model: trigger the instant price TOUCHES the
              line, fill at the line / gap open. This is how the strategy actually
              enters.
    next      fill at the next bar open O[t+1] (the conservative audit fix).
    open      LEGACY. Requires a break THROUGH the line by tol, fills at the line.
              Optimistic: silently drops the marginal touches a resting order takes.

Causal pivot confirmation is ON by default. Without it the refit can use pivots up
to K bars past the decision bar, which is a lookahead. --no-causal turns it off.
--legacy is shorthand for --fill open --no-causal.

CSV format: time,open,high,low,close[,volume]
    time may be epoch seconds, epoch milliseconds, or a datetime string. A header
    row is optional and skipped automatically.
"""
import argparse, os
from datetime import datetime, timezone
import numpy as np
from backtest_hull import run, load_series


def resolve_start(path, start_arg):
    if start_arg is None:
        return int(load_series(path)[0].min()) + 60 * 86400
    if start_arg.isdigit():
        return int(start_arg)
    return int(datetime.strptime(start_arg, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def main():
    ap = argparse.ArgumentParser(description="trendline-walk backtest")
    ap.add_argument("paths", nargs="+", help="one or more OHLC csv files")
    ap.add_argument("--start", default=None,
                    help="YYYY-MM-DD or epoch seconds (default: first bar + 60d)")
    ap.add_argument("--mult", type=float, default=1.0,
                    help="contract multiplier (only used if you add dollar P&L)")
    ap.add_argument("--cap", type=float, default=1e12,
                    help="risk cap in price*mult; default off")
    ap.add_argument("--maxspan", type=int, default=1200, help="max trendline age in bars")
    ap.add_argument("--fill", default="intrabar", choices=["open", "intrabar", "next"],
                    help="entry fill model (default intrabar == honest)")
    ap.add_argument("--no-causal", dest="causal", action="store_false",
                    help="turn OFF causal pivot confirmation (reproduces the old lookahead)")
    ap.set_defaults(causal=True)
    ap.add_argument("--legacy", action="store_true",
                    help="shorthand for --fill open --no-causal: reproduces the old inflated numbers")
    ap.add_argument("--name", default=None, help="override the symbol label")
    args = ap.parse_args()

    if args.legacy:
        args.fill, args.causal = "open", False
        print("*** LEGACY MODE: lookahead refit + optimistic fill. "
              "These numbers are inflated and are NOT the published result. ***\n")

    hdr = f"{'symbol':16s} {'trades':>6s} {'win%':>5s} {'totalR':>7s} {'avgR':>6s} {'PF':>5s} {'L/S':>7s}"
    print(f"fill={args.fill}, causal={args.causal}, maxspan={args.maxspan}\n")
    print(hdr); print("-" * len(hdr))
    allR = []
    for p in args.paths:
        name = args.name or os.path.splitext(os.path.basename(p))[0]
        s, tr, _, _ = run(name, p, args.mult, resolve_start(p, args.start),
                          CAP=args.cap, MAXSPAN=args.maxspan, fill=args.fill, causal=args.causal)
        allR += [x["R"] for x in tr]
        print(f"{s['symbol']:16s} {s['trades']:6d} {s['win']:5.0f} "
              f"{s['totalR']:+7.1f} {s['avgR']:+6.2f} {str(s['PF']):>5s} "
              f"{s['long']}/{s['short']}")
    if len(args.paths) > 1 and allR:
        a = np.array(allR)
        pf = a[a > 0].sum() / abs(a[a < 0].sum()) if (a < 0).any() else float("inf")
        print("-" * len(hdr))
        print(f"{'PORTFOLIO':16s} {len(a):6d} {100*(a>0.01).mean():5.0f} "
              f"{a.sum():+7.1f} {a.mean():+6.2f} {pf:5.2f}")


if __name__ == "__main__":
    main()
