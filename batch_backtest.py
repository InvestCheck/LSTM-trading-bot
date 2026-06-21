#!/usr/bin/env python3
"""Batch backtest over seed/*.csv. Prints a per symbol table and a portfolio total,
and writes trades_<SYM>.csv per symbol for the tier model.

Usage:
  python3 batch_backtest.py                   every seed/*.csv at MAXSPAN 24000
  python3 batch_backtest.py MGC PL HG SI PA    only these symbols
  python3 batch_backtest.py --maxspan 1200     different span
  python3 batch_backtest.py --warmup-days 60   history required before the first entry

Each symbol just needs seed/<SYM>.csv with columns time,open,high,low,close,volume
(epoch or datetime, the loader handles both). Drop in MGC, PL, HG, SI, PA, MCL, NQ, etc.
The detector is percentage based and accounts in R multiples, so contract size does not
matter here; one file per symbol is all it needs.

Leakage rule: the trade CSV puts signal time columns first (known at entry) and outcome
columns last (exit_time, exit, why, R_realized, ratcheted). Train the tier model ONLY on
the signal time columns. Never feed an outcome column to the model.
"""
import os, sys, glob, csv
from datetime import datetime, timezone
from backtest_hull import run, load_series

SEED_DIR = "seed"
OUT_DIR = "backtests"
MAXSPAN = 1200
WARMUP_DAYS = 60

# standard contract tick sizes, used only when --slip is set
TICKS = {"MGC": 0.10, "GC": 0.10, "SI": 0.005, "SIL": 0.005, "HG": 0.0005,
         "MHG": 0.0005, "PL": 0.10, "PA": 0.05, "CL": 0.01, "MCL": 0.01,
         "NQ": 0.25, "MNQ": 0.25, "ES": 0.25, "MES": 0.25}

SIG_COLS = ["symbol", "entry_time", "dir", "entry", "stop0", "R_px", "kind",
            "touches", "span_bars", "anchor_time", "slope", "stop_src"]
OUT_COLS = ["exit_time", "exit", "why", "R_realized", "ratcheted"]


def iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_args(argv):
    syms, maxspan, warmup, slip = [], MAXSPAN, WARMUP_DAYS, 0
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--maxspan":
            maxspan = int(argv[i + 1]); i += 2
        elif a == "--warmup-days":
            warmup = int(argv[i + 1]); i += 2
        elif a == "--slip":
            slip = float(argv[i + 1]); i += 2
        else:
            syms.append(a); i += 1
    return syms, maxspan, warmup, slip


def write_trades(path, sym, trades, T):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(SIG_COLS + OUT_COLS)
        for tr in trades:
            entry, stop0 = tr["entry"], tr["stop0"]
            touches = len(tr["tch"]) if isinstance(tr.get("tch"), (list, tuple)) else tr.get("tch")
            sig = [sym, iso(T[tr["t0"]]), tr["dir"], entry, stop0,
                   round(abs(entry - stop0), 4), tr["kind"], touches,
                   int(tr["t0"] - tr["a"]), iso(T[tr["a"]]), round(tr["m"], 8), tr["stop_src"]]
            outc = [iso(T[tr["exit_idx"]]), tr["exit"], tr["why"], tr["R"],
                    int(bool(tr.get("ratcheted")))]
            w.writerow(sig + outc)


def main():
    syms, maxspan, warmup, slip = parse_args(sys.argv)
    if not syms:
        syms = sorted(os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(SEED_DIR, "*.csv")))
    if not syms:
        print(f"no CSVs in {SEED_DIR}/. drop seed/<SYM>.csv files there."); return
    os.makedirs(OUT_DIR, exist_ok=True)

    cost = f", slippage {slip} tick/side" if slip else ""
    print(f"MAXSPAN {maxspan}, warmup {warmup}d{cost}, {len(syms)} symbol(s)\n")
    header = f"{'symbol':8s} {'trades':>6s} {'win%':>5s} {'totalR':>8s} {'avgR':>6s} {'PF':>5s}  range"
    print(header); print("-" * len(header))
    port_R, port_tr = 0.0, 0
    for sym in syms:
        path = os.path.join(SEED_DIR, f"{sym}.csv")
        if not os.path.exists(path):
            print(f"{sym:8s}  (missing {path})"); continue
        tick = TICKS.get(sym, 0.0)
        if slip and tick == 0.0:
            print(f"{sym:8s}  (no tick size known; add it to TICKS to model slippage)")
        T, O, H, L, C = load_series(path)
        start_ts = int(T.min()) + warmup * 86400
        summ, trades, _, _ = run(sym, path, 1.0, start_ts, CAP=1e12, MAXSPAN=maxspan,
                                 tick=tick, slip_ticks=slip)
        write_trades(os.path.join(OUT_DIR, f"trades_{sym}.csv"), sym, trades, T)
        pf = summ["PF"] if summ["PF"] is not None else 0
        rng = f"{iso(T.min())[:10]}..{iso(T.max())[:10]}"
        print(f"{sym:8s} {summ['trades']:6d} {summ['win']:5.0f} {summ['totalR']:+8.1f} "
              f"{summ['avgR']:+6.2f} {pf:5.2f}  {rng}")
        port_R += summ["totalR"]; port_tr += summ["trades"]
    print("-" * len(header))
    print(f"{'TOTAL':8s} {port_tr:6d} {'':5s} {port_R:+8.1f}")
    print(f"\ntrade records -> {OUT_DIR}/trades_<SYM>.csv  (signal time cols first, outcome cols last)")


if __name__ == "__main__":
    main()
