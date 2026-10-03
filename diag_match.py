#!/usr/bin/env python3
"""Why don't the trade files reproduce? Tries candidate explanations on a few
symbols and reports how much of each trade file each candidate recovers.

Usage (repo folder):  python3 diag_match.py DATA_DIR [SYM ...]   default GC ES ZN
"""
import sys, csv, os, tempfile, statistics as st
from batch_backtest import build_catalog, iso
from backtest_hull import run, load_series


def write_tmp(T, O, H, L, C):
    fd, p = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "open", "high", "low", "close", "volume"])
        for i in range(len(T)):
            w.writerow([int(T[i]), O[i], H[i], L[i], C[i], 0])
    return p


def score(path, T, ref, cut, **kw):
    _, trades, _, _ = run("x", path, 1.0, int(T.min()) + 60 * 86400, CAP=1e12, **kw)
    mine = {(iso(T[x["t0"]]), str(x["dir"])): x for x in trades if iso(T[x["t0"]]) <= cut}
    theirs = {(r["entry_time"], r["dir"]): r for r in ref}
    both = set(mine) & set(theirs)
    scale = ""
    if both:
        rr = [abs(mine[k]["entry"] - mine[k]["stop0"]) / float(theirs[k]["R_px"])
              for k in both if float(theirs[k]["R_px"]) > 0]
        if rr: scale = f"  Rpx ratio {st.median(rr):.4g}"
    return f"{len(both)}/{len(theirs)} of file recovered, {len(mine) - len(both)} extra{scale}"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 diag_match.py DATA_DIR [SYM ...]")
    cat = build_catalog(sys.argv[1])
    for s in sys.argv[2:] or ["GC", "ES", "ZN"]:
        ref = list(csv.DictReader(open(f"backtests/trades_{s}.csv")))
        cut = max(r["entry_time"] for r in ref)
        T, O, H, L, C = load_series(cat[s])
        print(f"\n{s}: file has {len(ref)} trades, first {ref[0]['entry_time']}, last {cut}")
        print(f"  data file runs {iso(T.min())} .. {iso(T.max())}")
        # data truncated at the trade files' cutoff
        last_exit = max(r["exit_time"] for r in ref)
        n = sum(1 for t in T if iso(t) <= last_exit) + 400
        tmp = write_tmp(T[:n], O[:n], H[:n], L[:n], C[:n])
        full = cat[s]
        try:
            for label, path, Tx, kw in [
                ("frozen 2160/17520, full data     ", full, T, dict(MINSPAN=2160, MAXSPAN=17520)),
                ("frozen 2160/17520, data to June  ", tmp, T[:n], dict(MINSPAN=2160, MAXSPAN=17520)),
                ("2160/24000                       ", full, T, dict(MINSPAN=2160, MAXSPAN=24000)),
                ("168/17520                        ", full, T, dict(MINSPAN=168, MAXSPAN=17520)),
                ("168/1200 (old defaults)          ", full, T, dict(MINSPAN=168, MAXSPAN=1200)),
                ("2160/17520, fill=open, causal off", full, T, dict(MINSPAN=2160, MAXSPAN=17520, fill="open", causal=False)),
            ]:
                print(f"  {label} {score(path, Tx, ref, cut, **kw)}")
        finally:
            os.remove(tmp)


if __name__ == "__main__":
    main()
