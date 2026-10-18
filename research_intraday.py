#!/usr/bin/env python3
"""The trendline engine on intraday bars: 5, 15 and 30 minute (and 1 minute on
request), built from the 1 minute files.

Same engine as the hourly protocol (backtest_hull.run, intrabar fill, causal,
2 ticks per round trip) plus commissions, with the span window scaled to the
bar. On hourly bars the protocol's lines span 90 days to 2 years; intraday the
candidate windows are, in session days:

  short   0.5 to 5       medium   2 to 20       long   10 to 90

Per timeframe the window with the best exploration (2008 to 2016) net avgR is
the one tested on the holdout (2017 to 2026). One test per timeframe, PASS =
net avgR > 0 and monthly block bootstrap t > 2.2 (three tests). Instrument cost
filter as in the protocol: 2 ticks / median R_px <= 0.10 on the exploration
half, applied per timeframe and window before the holdout is read.

Trades can hold overnight here; the prop firm version (flat at the close) is
a separate step if anything passes. Costs: 2 ticks + COMM per side on the
micro contract, in R.

Usage (repo folder):  python3 research_intraday.py DATA_DIR_1m [--tf 5 15 30] [--symbols ...]
Writes research/intraday_report.md and research/intraday_trades_<tf>m_<window>.csv.
"""
import os, sys, csv, math, glob, re, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import run, load_series
from instruments import TICKS

OUT = "research"; BARS = os.path.join(OUT, "intraday_bars")
SPLIT_YEAR = 2017
COMM = 1.5
BOOT_REPS, SEED = 400, 11
WINDOWS = {"short": (0.5, 5), "medium": (2, 20), "long": (10, 90)}     # session days
SESSION_MIN = 23 * 60                                                   # minutes per session
COST_CAP = 0.10
MICROS = {
    "ES": ("MES", 5), "NQ": ("MNQ", 2), "RTY": ("M2K", 5), "YM": ("MYM", 0.5), "GC": ("MGC", 10), "SI": ("SIL", 1000),
    "HG": ("MHG", 2500), "CL": ("MCL", 100), "NG": ("QG", 2500), "E6": ("M6E", 12500), "A6": ("M6A", 10000),
    "B6": ("M6B", 6250), "J1": ("MJY", 1250000), "E1": ("MSF", 12500),
}


def resample_file(src, dst, tf):
    """Write tf minute bars (aligned to the 18:00 ET open) in the vendor format. Cached."""
    if os.path.exists(dst): return
    ts, o, h, l, c, v = [], [], [], [], [], []; day_cache = {}
    with open(src) as f:
        for line in f:
            p = line.split(",")
            if len(p) < 6: continue
            d = p[0][:10]; base = day_cache.get(d)
            if base is None:
                base = int(datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), tzinfo=timezone.utc).timestamp()); day_cache[d] = base
            ts.append(base + int(p[0][11:13]) * 3600 + int(p[0][14:16]) * 60)
            o.append(float(p[1])); h.append(float(p[2])); l.append(float(p[3])); c.append(float(p[4])); v.append(float(p[5]))
    T = np.array(ts, np.int64); O, H, L, C, V = map(np.array, (o, h, l, c, v))
    if tf > 1:
        sess = (T - 60 + 6 * 3600) // 86400; off = (T - 60 + 6 * 3600) % 86400
        key = sess * 100000 + off // (tf * 60)
        idx = np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]])); ends = np.concatenate([idx[1:], [len(T)]]) - 1
        T, O, H, L, C, V = T[ends], O[idx], np.maximum.reduceat(H, idx), np.minimum.reduceat(L, idx), C[ends], np.add.reduceat(V, idx)
    with open(dst, "w") as f:
        for i in range(len(T)):
            f.write(f"{datetime.fromtimestamp(int(T[i]), timezone.utc):%Y-%m-%d %H:%M:%S},{O[i]:.10g},{H[i]:.10g},{L[i]:.10g},{C[i]:.10g},{V[i]:.0f}\n")


def block_t(vals, months):
    by = defaultdict(list)
    for v, m in zip(vals, months): by[m].append(v)
    keys = list(by); rng = np.random.default_rng(SEED); means = []
    for _ in range(BOOT_REPS):
        pick = rng.integers(0, len(keys), len(keys)); means.append(np.mean([x for i in pick for x in by[keys[i]]]))
    m = float(np.mean(vals)); sd = float(np.std(means))
    return m, (m / sd if sd > 0 else float("nan"))


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_intraday.py DATA_DIR_1m [--tf 5 15 30] [--symbols ...]")
    tfs = [5, 15, 30]; syms = list(MICROS)
    if "--tf" in args:
        tfs = []
        for a in args[args.index("--tf") + 1:]:
            if a.startswith("--"): break
            tfs.append(int(a))
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    os.makedirs(BARS, exist_ok=True)
    rows = []                                   # one per trade
    for sym in syms:
        if sym not in cat: print(f"{sym}: no 1 minute file"); continue
        tick = TICKS.get(sym, 0.0); micro, mult = MICROS[sym]
        for tf in tfs:
            path = os.path.join(BARS, f"{sym}_{tf}m.csv"); t0 = time.time()
            resample_file(cat[sym], path, tf)
            T = load_series(path)[0]; bpd = SESSION_MIN / tf
            start_ts = int(T.min()) + 60 * 86400
            for wname, (lo_d, hi_d) in WINDOWS.items():
                minspan, maxspan = int(lo_d * bpd), int(hi_d * bpd)
                summ, trades, _, _ = run(sym, path, 1.0, start_ts, SPANDAYS=lo_d * 0.08, MINSPAN=minspan, MAXSPAN=maxspan,
                                         CAP=1e12, tick=tick, slip_ticks=1.0, fill="intrabar", causal=True)
                for tr in trades:
                    R_px = abs(tr["entry"] - tr["stop0"])
                    if R_px <= 0: continue
                    et = datetime.fromtimestamp(int(T[tr["t0"]]), timezone.utc); xt = datetime.fromtimestamp(int(T[tr["exit_idx"]]), timezone.utc)
                    net = tr["R"] - 2 * COMM / (R_px * mult)              # engine R already carries the 2 tick slippage
                    rows.append(dict(symbol=sym, micro=micro, tf=tf, window=wname, entry_time=et.strftime("%Y-%m-%d %H:%M"),
                                     exit_time=xt.strftime("%Y-%m-%d %H:%M"), month=et.strftime("%Y-%m"), year=et.year,
                                     dir=tr["dir"], entry=tr["entry"], stop0=tr["stop0"], exit=tr["exit"], why=tr["why"],
                                     R_px=R_px, R_gross=tr["R"], R=net, cost_ticks=2 * tick / R_px if tick else 0,
                                     bars_held=tr["exit_idx"] - tr["t0"], overnight=int(et.date() != xt.date())))
                print(f"{sym:4s} {tf:2d}m {wname:6s} {len(trades):5d} trades  ({time.time() - t0:.0f}s)", flush=True)

    L = ["# Trendline engine on intraday bars (CME micro universe)\n",
         "Same engine as the hourly protocol (intrabar fill, causal, 2 ticks per round trip) plus commissions on the micro "
         "contract, span windows scaled to the bar. Per timeframe the window with the best exploration net avgR is tested on "
         "the holdout; one test per timeframe, PASS = net avgR > 0 and monthly block bootstrap t > 2.2. Instrument cost cap "
         f"(2 ticks / median R_px <= {COST_CAP}) set on the exploration half.\n"]
    for tf in tfs:
        L += [f"\n## {tf} minute bars\n", "| window | set | instruments | trades | per instr/yr | net avgR | gross avgR | boot t | win% | overnight | median cost (R) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        best, best_m = None, -9; chosen = {}
        for wname in WINDOWS:
            sub = [r for r in rows if r["tf"] == tf and r["window"] == wname]
            # cost cap per instrument on the exploration half
            keep = set()
            for sym in syms:
                ex = [r for r in sub if r["symbol"] == sym and r["year"] < SPLIT_YEAR]
                if len(ex) >= 30 and np.median([r["cost_ticks"] for r in ex]) <= COST_CAP: keep.add(sym)
            chosen[wname] = keep
            ex = [r for r in sub if r["symbol"] in keep and r["year"] < SPLIT_YEAR]
            if ex:
                m, t = block_t([r["R"] for r in ex], [r["month"] for r in ex]); yrs = SPLIT_YEAR - 2008
                L.append(f"| {wname} | explore | {len(keep)} | {len(ex)} | {len(ex) / max(1, len(keep)) / yrs:.0f} | {m:+.4f} | "
                         f"{np.mean([r['R_gross'] for r in ex]):+.4f} | {t:.2f} | {np.mean([r['R'] > 0 for r in ex]) * 100:.0f}% | "
                         f"{np.mean([r['overnight'] for r in ex]) * 100:.0f}% | {np.median([r['cost_ticks'] for r in ex]):.3f} |")
                if m > best_m: best_m, best = m, wname
            else:
                L.append(f"| {wname} | explore | 0 | 0 | | | | | | | |")
        for wname in WINDOWS:
            keep = chosen[wname]
            ho = [r for r in rows if r["tf"] == tf and r["window"] == wname and r["symbol"] in keep and r["year"] >= SPLIT_YEAR]
            if not ho: L.append(f"| {wname} | holdout | 0 | 0 | | | | | | | |"); continue
            m, t = block_t([r["R"] for r in ho], [r["month"] for r in ho]); yrs = 9.7
            tag = " (THE TEST)" if wname == best else ""
            L.append(f"| {wname} | holdout{tag} | {len(keep)} | {len(ho)} | {len(ho) / max(1, len(keep)) / yrs:.0f} | {m:+.4f} | "
                     f"{np.mean([r['R_gross'] for r in ho]):+.4f} | {t:.2f} | {np.mean([r['R'] > 0 for r in ho]) * 100:.0f}% | "
                     f"{np.mean([r['overnight'] for r in ho]) * 100:.0f}% | {np.median([r['cost_ticks'] for r in ho]):.3f} |")
            if wname == best:
                L.append(f"\n**{tf}m, {wname} window: holdout net avgR {m:+.4f}, t {t:.2f} -> {'PASS' if (m > 0 and t > 2.2) else 'no'}**\n")
                L += ["| instrument | trades | net avgR | boot t | win% |", "|---|---|---|---|---|"]
                for sym in syms:
                    s_ = [r for r in ho if r["symbol"] == sym]
                    if s_:
                        mm, tt = block_t([r["R"] for r in s_], [r["month"] for r in s_])
                        L.append(f"| {sym} | {len(s_)} | {mm:+.4f} | {tt:.2f} | {np.mean([r['R'] > 0 for r in s_]) * 100:.0f}% |")
        for wname in WINDOWS:
            sub = [r for r in rows if r["tf"] == tf and r["window"] == wname]
            if sub:
                with open(os.path.join(OUT, f"intraday_trades_{tf}m_{wname}.csv"), "w", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(sub[0].keys())); w.writeheader(); w.writerows(sub)
    open(os.path.join(OUT, "intraday_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/intraday_report.md and {OUT}/intraday_trades_<tf>m_<window>.csv")


if __name__ == "__main__":
    main()
