#!/usr/bin/env python3
"""Broker free check before building the live bot.

1. Times one full engine pass per frozen instrument at the protocol config.
   The live bot reruns the engine over full history every hour, so the total
   must fit comfortably inside an hour on the droplet.
2. Confirms the engine at this config reproduces backtests/trades_<SYM>.csv
   (same entry times and directions), i.e. the files are the frozen config.
3. Reports the latest exit in those files, which is the true data cutoff the
   universe was measured on.

Usage (repo folder):  python3 timing_check.py DATA_DIR
"""
import sys, time, csv
from batch_backtest import build_catalog, iso
from backtest_hull import run, load_series
from ib_contracts import UNIVERSE


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 timing_check.py DATA_DIR")
    cat = build_catalog(sys.argv[1])
    total, slowest, latest_exit, diffs, missing = 0.0, (0.0, ""), "", [], []
    for s in UNIVERSE:
        if s not in cat:
            print(f"{s:6s} MISSING from data dir"); missing.append(s); continue
        T = load_series(cat[s])[0]
        t0 = time.time()
        _, trades, _, _, _ = run(s, cat[s], 1.0, int(T.min()) + 60 * 86400, CAP=1e12,
                                 MINSPAN=2160, MAXSPAN=17520, fill="intrabar",
                                 causal=True, return_open=True)
        dt = time.time() - t0
        total += dt
        slowest = max(slowest, (dt, s))
        ref = list(csv.DictReader(open(f"backtests/trades_{s}.csv")))
        if ref:
            latest_exit = max(latest_exit, max(r["exit_time"] for r in ref))
            cut = max(r["entry_time"] for r in ref)
            mine = [(iso(T[x["t0"]]), str(x["dir"])) for x in trades if iso(T[x["t0"]]) <= cut]
            theirs = [(r["entry_time"], r["dir"]) for r in ref]
            ok = mine == theirs
        else:
            ok = not trades
        if not ok:
            diffs.append(s)
        print(f"{s:6s} {len(T):7d} bars {dt:6.1f}s  {'match' if ok else 'DIFFERENT'}")
    print(f"\none hourly pass: {total / 60:.1f} min on this machine, "
          f"slowest {slowest[1]} {slowest[0]:.1f}s")
    print(f"trade files reproduced: {len(UNIVERSE) - len(diffs) - len(missing)}/{len(UNIVERSE)}"
          + (f"  DIFFERENT: {' '.join(diffs)}" if diffs else ""))
    if missing:
        print(f"missing: {' '.join(missing)}")
    print(f"latest exit in trade files: {latest_exit}")


if __name__ == "__main__":
    main()
