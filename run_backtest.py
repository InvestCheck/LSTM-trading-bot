#!/usr/bin/env python3
"""Run the trendline-walk backtest on one or more OHLC CSV files.

Examples
--------
    python run_backtest.py data/gold.csv
    python run_backtest.py data/GC.csv data/SI.csv data/HG.csv
    python run_backtest.py data/GC.csv --start 2008-03-01 --name Gold

CSV format: time,open,high,low,close[,volume]
    time may be epoch seconds, epoch milliseconds, or a datetime string
    (e.g. "2008-01-02 09:00:00", "01/02/2008 09:00", ISO 8601). A header
    row is optional and skipped automatically. Works with both the old
    TradingView epoch exports and FirstRateData datetime files.

Notes
-----
    * The risk cap is OFF by default, so the contract multiplier does not
      affect the R results (R is unit-free). It only matters if you later
      add a dollar P&L layer.
    * Default start is 60 days after the first bar, to warm up the 200 EMA
      and ATR. Override with --start.
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
    ap.add_argument("--name", default=None, help="override the symbol label")
    args = ap.parse_args()

    hdr = f"{'symbol':16s} {'trades':>6s} {'win%':>5s} {'totalR':>7s} {'avgR':>6s} {'PF':>5s} {'L/S':>7s}"
    print(hdr)
    print("-" * len(hdr))
    allR = []
    for p in args.paths:
        name = args.name or os.path.splitext(os.path.basename(p))[0]
        s, tr, _, _ = run(name, p, args.mult, resolve_start(p, args.start), CAP=args.cap)
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
