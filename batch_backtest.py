#!/usr/bin/env python3
"""Batch backtest over seed/*.csv. Prints a per symbol table and a portfolio total,
and writes trades_<SYM>.csv per symbol for the tier model.

Usage:
  python3 batch_backtest.py                   every seed/*.csv at MAXSPAN 24000
  python3 batch_backtest.py MGC PL HG SI PA    only these symbols
  python3 batch_backtest.py --maxspan 1200     different span
  python3 batch_backtest.py --warmup-days 60   history required before the first entry
  python3 batch_backtest.py --fill intrabar    fill model: one of {open, intrabar, next}
  python3 batch_backtest.py --no-causal        disable causal detection (default: causal on)
  python3 batch_backtest.py --legacy           inflated legacy mode (fill=open, causal=off)
  python3 batch_backtest.py --data-dir DIR     read DIR instead of seed/ (FirstRateData
                                               .txt files resolve to symbols the same way
                                               the scan notebook does)

Defaults are the published configuration: fill='intrabar', causal=True. --fill must be
one of {open, intrabar, next}; any other value is a hard error. --legacy restores the old
fill='open', causal=False behaviour and prints a warning because those numbers are inflated
and are NOT the published result.

Each symbol just needs seed/<SYM>.csv with columns time,open,high,low,close,volume
(epoch or datetime, the loader handles both). Drop in MGC, PL, HG, SI, PA, MCL, NQ, etc.
The detector is percentage based and accounts in R multiples, so contract size does not
matter here; one file per symbol is all it needs.

Leakage rule: the trade CSV puts signal time columns first (known at entry) and outcome
columns last (exit_time, exit, why, R_realized, ratcheted). Train the tier model ONLY on
the signal time columns. Never feed an outcome column to the model.
"""
import os, re, sys, glob, csv
from datetime import datetime, timezone
from backtest_hull import run, load_series

SEED_DIR = "seed"
OUT_DIR = "backtests"
MAXSPAN = 1200
WARMUP_DAYS = 60

# Tick sizes come from instruments.py, which covers all 131 scanned symbols.
# A symbol missing from that mapping gets zero slippage and is warned about.
from instruments import TICKS


def symbol_of(path):
    """FirstRateData filename to symbol. Same rule as the scan notebook, so a
    directory of A6_full_1hour_continuous_ratio_adjusted.txt files resolves to
    the symbols used in instruments.py and the results CSVs."""
    b = os.path.basename(path)
    b = re.sub(r"_full_1hour.*$", "", b)
    b = re.sub(r"\.(csv|txt)$", "", b)
    b = re.sub(r"^\d+_", "", b)
    return b


def build_catalog(data_dir):
    """symbol -> path for every .txt/.csv in data_dir."""
    paths = sorted(glob.glob(os.path.join(data_dir, "*.txt")) +
                   glob.glob(os.path.join(data_dir, "*.csv")))
    return {symbol_of(p): p for p in paths}

SIG_COLS = ["symbol", "entry_time", "dir", "entry", "stop0", "R_px", "kind",
            "touches", "span_bars", "anchor_time", "slope", "stop_src"]
OUT_COLS = ["exit_time", "exit", "why", "R_realized", "ratcheted"]


def iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M")


VALID_FILL = ("open", "intrabar", "next")


def parse_args(argv):
    syms, maxspan, warmup, slip, fill, causal = [], MAXSPAN, WARMUP_DAYS, 0, 'intrabar', True
    legacy = False
    data_dir = SEED_DIR
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--maxspan":
            maxspan = int(argv[i + 1]); i += 2
        elif a == "--warmup-days":
            warmup = int(argv[i + 1]); i += 2
        elif a == "--slip":
            slip = float(argv[i + 1]); i += 2
        elif a == "--fill":
            fill = argv[i + 1]; i += 2
            if fill not in VALID_FILL:
                sys.exit(f"error: --fill must be one of {{{', '.join(VALID_FILL)}}}, "
                         f"got {fill!r}")
        elif a == "--no-causal":
            causal = False; i += 1
        elif a == "--data-dir":
            data_dir = argv[i + 1]; i += 2
        elif a == "--legacy":
            legacy = True; i += 1
        else:
            syms.append(a); i += 1
    # --legacy wins regardless of flag order: force the inflated config after parsing.
    if legacy:
        fill, causal = 'open', False
        print("WARNING: --legacy uses fill='open', causal=False. These numbers are "
              "inflated and are NOT the published result.", file=sys.stderr)
    return syms, maxspan, warmup, slip, fill, causal, data_dir


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
    syms, maxspan, warmup, slip, fill, causal, data_dir = parse_args(sys.argv)
    catalog = build_catalog(data_dir)
    if not catalog:
        print(f"no .txt or .csv files in {data_dir}/. pass --data-dir to point at "
              f"the price data, or drop seed/<SYM>.csv files in {SEED_DIR}/.")
        return
    missing = [s for s in syms if s not in catalog]
    if missing:
        print(f"not found in {data_dir}/: {', '.join(missing)}")
    syms = [s for s in syms if s in catalog] or sorted(catalog)
    no_tick = [s for s in syms if s not in TICKS]
    if slip and no_tick:
        print(f"WARNING: no tick size for {len(no_tick)} symbol(s), they get ZERO "
              f"slippage: {', '.join(no_tick)}\n", file=sys.stderr)
    os.makedirs(OUT_DIR, exist_ok=True)

    cost = f", slippage {slip} tick/side" if slip else ""
    print(f"MAXSPAN {maxspan}, warmup {warmup}d, fill={fill}, causal={causal}{cost}, "
          f"{len(syms)} symbol(s) from {data_dir}/\n")
    header = f"{'symbol':8s} {'trades':>6s} {'win%':>5s} {'totalR':>8s} {'avgR':>6s} {'PF':>5s}  range"
    print(header); print("-" * len(header))
    port_R, port_tr = 0.0, 0
    for sym in syms:
        path = catalog[sym]
        tick = TICKS.get(sym, 0.0)
        T, O, H, L, C = load_series(path)
        start_ts = int(T.min()) + warmup * 86400
        summ, trades, _, _ = run(sym, path, 1.0, start_ts, CAP=1e12, MAXSPAN=maxspan,
                                 tick=tick, slip_ticks=slip, fill=fill, causal=causal)
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
