#!/usr/bin/env python3
"""Data revised, or engine changed?

For trades that appear in both the June trade file and a rerun on current data,
compares entry prices. If the current history is the June history times one
constant, the ratio is identical for every trade and the missing trades must
come from an engine change. If the ratio drifts across years, the vendor
revised the history itself.

Usage (repo folder):  python3 diag_scale.py DATA_DIR [SYM ...]   default GC ES ZN
"""
import sys, csv, statistics as st
from collections import defaultdict
from batch_backtest import build_catalog, iso
from backtest_hull import run, load_series


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 diag_scale.py DATA_DIR [SYM ...]")
    cat = build_catalog(sys.argv[1])
    for s in sys.argv[2:] or ["GC", "ES", "ZN"]:
        ref = {(r["entry_time"], r["dir"]): r
               for r in csv.DictReader(open(f"backtests/trades_{s}.csv"))}
        T = load_series(cat[s])[0]
        _, trades, _, _ = run(s, cat[s], 1.0, int(T.min()) + 60 * 86400, CAP=1e12,
                              MINSPAN=2160, MAXSPAN=17520, fill="intrabar", causal=True)
        by_year = defaultdict(list)
        for x in trades:
            k = (iso(T[x["t0"]]), str(x["dir"]))
            if k in ref and float(ref[k]["entry"]):
                by_year[k[0][:4]].append(x["entry"] / float(ref[k]["entry"]))
        allr = [r for v in by_year.values() for r in v]
        spread = (max(allr) - min(allr)) / st.median(allr)
        print(f"\n{s}: {len(allr)} matched trades, ratio min {min(allr):.6f} "
              f"max {max(allr):.6f}  spread {spread:.4%}")
        print("  " + "  ".join(f"{y}:{st.median(v):.4f}" for y, v in sorted(by_year.items())))
        print("  -> " + ("ONE CONSTANT: history only rescaled, look at engine changes"
                         if spread < 1e-5 else
                         "DRIFTS: vendor revised the history"))


if __name__ == "__main__":
    main()
