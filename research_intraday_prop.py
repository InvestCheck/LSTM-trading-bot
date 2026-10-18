#!/usr/bin/env python3
"""Prop firm version of the intraday trendline engine: the trades from
research_intraday.py cut flat at the close of the entry session with re entry at
the next open, instrument set and entry hours chosen on the exploration half only,
then every prop plan run on the holdout trades through prop_sim.py.

Why this exists: on a one time fee plan the firm's drawdown is an option, so a
strategy with zero or slightly negative net edge can still have positive expected
value per attempt. The intraday engine's gross edge is about zero and its net edge
(after commissions) is -0.05 to -0.21R depending on the bar size; this tests
whether any of it clears the fee.

Per timeframe (long window, the one the main study picked on exploration):
  1. flat at the close: a trade still open at the last bar ending by 16:45 ET of
     its session exits at that bar's close, a tick worse. If the engine still holds
     at the next session's open (18:00 ET) it re enters at that open plus a tick as
     a new leg, with its own commissions, until the engine exits. Each leg is one
     day's P&L. Trades entered after the flat bar are dropped.
  2. instrument set: exploration (2008 to 2016) median cost <= 0.10R and
     exploration flat net avgR >= THR, 30+ legs; fixed before the holdout is read
  3. entry hours (ET, hour of the original signal): exploration flat net avgR >= THR
     with 100+ legs on the kept instruments; the by hour table shows exploration
     and holdout side by side
  4. holdout (2017 to 2026) flat net avgR and t for instruments only and for
     instruments + hours (the deployed version), then prop_sim on the deployed
     holdout legs (research/intraday_prop_<tf>m.csv -> research/prop_intraday_<tf>m.md)

This is a second look at the same holdout the main intraday study already used,
so a pass here is weaker than a first look would be.

Usage (repo folder):  python3 research_intraday_prop.py [--tf 30 15 5] [--window long] [--thr -0.05] [--no-hours] [--no-sim]
"""
import os, sys, csv, subprocess
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from instruments import TICKS
from research_intraday import MICROS, COMM, BARS, OUT, SPLIT_YEAR, COST_CAP, block_t

FLAT_MIN = 16 * 60 + 45
MIN_HOUR_N = 100


def load_bars(path):
    ts, o, c = [], [], []; cache = {}
    with open(path) as f:
        for line in f:
            p = line.split(","); d = p[0][:10]; base = cache.get(d)
            if base is None:
                base = int(datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), tzinfo=timezone.utc).timestamp()); cache[d] = base
            ts.append(base + int(p[0][11:13]) * 3600 + int(p[0][14:16]) * 60); o.append(float(p[1])); c.append(float(p[4]))
    T = np.array(ts, np.int64); O = np.array(o); C = np.array(c)
    sess = (T - 60 + 6 * 3600) // 86400; mod = ((T // 60) % 1440).astype(int)
    idx = np.flatnonzero(mod <= FLAT_MIN); s = sess[idx]
    u, first = np.unique(s[::-1], return_index=True); last = dict(zip(u.tolist(), idx[::-1][first].tolist()))
    return T, O, C, sess, last


def ts(s): return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def legs_of(r, bars, tick, micro, mult):
    """Split one engine trade into session legs (flat at the close, re entry at the next open)."""
    T, O, C, sess, last = bars; n = len(T)
    d = int(r["dir"]); R_px = float(r["R_px"]); cost = 2 * COMM / (R_px * mult)
    i0 = int(np.searchsorted(T, ts(r["entry_time"]))); ix = int(np.searchsorted(T, ts(r["exit_time"])))
    if i0 >= n: return []
    cur_i, cur_entry, hour, out, leg = i0, float(r["entry"]), int(ts(r["entry_time"]) // 3600 % 24), [], 0
    while True:
        fl = last.get(int(sess[cur_i]))
        if fl is None or cur_i > fl: break                                     # entered after the flat bar
        if ix > fl: xpx, why, xi, cut = C[fl] - d * tick, "flat", fl, 1
        else: xpx, why, xi, cut = float(r["exit"]), r["why"], ix, 0
        R = (xpx - cur_entry) * d / R_px - cost; t_in = datetime.fromtimestamp(int(T[cur_i]), timezone.utc)
        out.append(dict(session=datetime.fromtimestamp(int(T[cur_i]) + 6 * 3600, timezone.utc).strftime("%Y-%m-%d"), symbol=r["symbol"], micro=micro,
                        tf=int(r["tf"]), entry_time=t_in.strftime("%Y-%m-%d %H:%M"), leg=leg, hour=hour, dir=d, R_px=R_px, R_unit=R_px * mult, R=R,
                        R_hold=float(r["R"]), pnl_usd=R * R_px * mult, why=why, cut=cut, year=t_in.year, month=t_in.strftime("%Y-%m"), cost=float(r["cost_ticks"])))
        if not cut: break
        nxt = fl + 1
        while nxt < n and sess[nxt] == sess[fl]: nxt += 1
        if nxt >= n or ix < nxt: break                                         # engine is out before the next open
        cur_i, cur_entry, leg = nxt, O[nxt] + d * tick, leg + 1
    return out


def main():
    args = sys.argv[1:]
    tfs = [30, 15, 5]; window = "long"; thr = -0.05
    if "--tf" in args:
        tfs = []
        for a in args[args.index("--tf") + 1:]:
            if a.startswith("--"): break
            tfs.append(int(a))
    if "--window" in args: window = args[args.index("--window") + 1]
    if "--thr" in args: thr = float(args[args.index("--thr") + 1])
    use_hours = "--no-hours" not in args
    L = ["# Intraday trendline engine, prop firm version (flat at the close, re entry at the open)\n",
         f"Trades from research_intraday.py ({window} window) cut at the last bar ending by 16:45 ET of each session and re entered at the next "
         f"18:00 ET open while the engine still holds; each leg is one day's P&L with its own costs. Instrument set and entry hours fixed on "
         f"exploration: median cost <= {COST_CAP}R, flat net avgR >= {thr:+.2f} (hours need {MIN_HOUR_N}+ legs). Holdout 2017 to 2026 is a second "
         "look (the main study already used it).\n"]
    for tf in tfs:
        src = os.path.join(OUT, f"intraday_trades_{tf}m_{window}.csv")
        if not os.path.exists(src): print(f"{src} missing (run research_intraday.py first)"); continue
        rows = list(csv.DictReader(open(src))); bars = {}; out = []
        for r in rows:
            sym = r["symbol"]
            if sym not in bars: bars[sym] = load_bars(os.path.join(BARS, f"{sym}_{tf}m.csv"))
            out += legs_of(r, bars[sym], TICKS.get(sym, 0.0), *MICROS[sym])
        keep = []
        L += [f"\n## {tf} minute bars, {window} window\n", "| instrument | explore legs | explore flat avgR | explore hold avgR (engine) | kept | holdout legs | holdout flat avgR | t |",
              "|---|---|---|---|---|---|---|---|"]
        for sym in MICROS:
            ex = [r for r in out if r["symbol"] == sym and r["year"] < SPLIT_YEAR]; ho = [r for r in out if r["symbol"] == sym and r["year"] >= SPLIT_YEAR]
            if not ex: continue
            m_ex = np.mean([r["R"] for r in ex]); ok = len(ex) >= 30 and np.median([r["cost"] for r in ex]) <= COST_CAP and m_ex >= thr
            if ok: keep.append(sym)
            mh, th = block_t([r["R"] for r in ho], [r["month"] for r in ho]) if ho else (float("nan"), float("nan"))
            L.append(f"| {sym} | {len(ex)} | {m_ex:+.4f} | {np.mean([r['R_hold'] for r in ex]):+.4f} | {'yes' if ok else ''} | {len(ho)} | {mh:+.4f} | {th:.2f} |")
        ex = [r for r in out if r["symbol"] in keep and r["year"] < SPLIT_YEAR]; ho = [r for r in out if r["symbol"] in keep and r["year"] >= SPLIT_YEAR]
        if not ho: L.append(f"\nNo instrument kept at {tf}m."); print(f"{tf}m: no instrument kept"); continue
        # entry hour table on the kept instruments, hours chosen on exploration
        L += [f"\nBy entry hour (ET, hour of the original signal), kept instruments {keep}:\n", "| hour | explore legs | explore avgR | kept | holdout legs | holdout avgR |", "|---|---|---|---|---|---|"]
        hours = []
        for h in range(24):
            e = [r["R"] for r in ex if r["hour"] == h]; o = [r["R"] for r in ho if r["hour"] == h]
            if not e and not o: continue
            ok = len(e) >= MIN_HOUR_N and np.mean(e) >= thr
            if ok: hours.append(h)
            L.append(f"| {h:02d} | {len(e)} | {np.mean(e) if e else float('nan'):+.4f} | {'yes' if ok else ''} | {len(o)} | {np.mean(o) if o else float('nan'):+.4f} |")
        me, te = block_t([r["R"] for r in ex], [r["month"] for r in ex]); mh, th = block_t([r["R"] for r in ho], [r["month"] for r in ho])
        L.append(f"\n**{tf}m instruments only: explore flat net avgR {me:+.4f} (t {te:.2f}, n {len(ex)}); holdout {mh:+.4f} (t {th:.2f}, n {len(ho)}, "
                 f"{len(ho) / 9.7 / 252:.1f} legs per day, re entry legs {np.mean([r['leg'] > 0 for r in ho]) * 100:.0f}%, win {np.mean([r['R'] > 0 for r in ho]) * 100:.0f}%)**")
        dep = ho
        if use_hours and hours:
            ex2 = [r for r in ex if r["hour"] in hours]; dep = [r for r in ho if r["hour"] in hours]
            me, te = block_t([r["R"] for r in ex2], [r["month"] for r in ex2]); mh, th = block_t([r["R"] for r in dep], [r["month"] for r in dep]) if dep else (float("nan"), float("nan"))
            L.append(f"\n**{tf}m instruments + hours {hours}: explore {me:+.4f} (t {te:.2f}, n {len(ex2)}); holdout {mh:+.4f} (t {th:.2f}, n {len(dep)}, "
                     f"{len(dep) / 9.7 / 252:.1f} legs per day) -> {'PASS' if (dep and mh > 0 and th > 2.2) else 'no'}**")
        elif use_hours: L.append(f"\nNo entry hour clears {thr:+.2f} on exploration; prop sim on instruments only.")
        if not dep: continue
        path = os.path.join(OUT, f"intraday_prop_{tf}m.csv")
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(dep[0].keys())); w.writeheader(); w.writerows(sorted(dep, key=lambda r: (r["session"], r["entry_time"])))
        print("\n".join(L[-40:]), flush=True)
        if "--no-sim" not in args:
            subprocess.run([sys.executable, "prop_sim.py", "--trades", path], check=True)
            rep = os.path.join(OUT, f"prop_intraday_{tf}m.md"); os.replace(os.path.join(OUT, "prop_report.md"), rep)
            L.append(f"\nProp plans on the deployed holdout legs: {rep}")
    open(os.path.join(OUT, "intraday_prop_report.md"), "w").write("\n".join(L) + "\n")
    print(f"\n-> {OUT}/intraday_prop_report.md, intraday_prop_<tf>m.csv, prop_intraday_<tf>m.md")


if __name__ == "__main__":
    main()
