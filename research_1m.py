#!/usr/bin/env python3
"""1 minute data on the v2 trade set.

A. Fill realism (calibration, not a decision). For every v2 trade, walk the
   1 minute bars of the entry hour to the first minute that breaches the resting
   order level, and price the fill three ways:
     line   at the level (what the backtest assumes, minus nothing)
     mid    midpoint of level and that minute's extreme beyond it
     worst  that minute's extreme
   Reports slippage versus the line in ticks and in R, and the share of trades
   where the hour's first minute already opened beyond the level (gap fills).

B. 1 minute confirmation entry (candidate). Enter on the first minute whose
   close is beyond the refit line, filled at the next minute's open; skip the
   trade if no minute closes beyond it within the entry hour. Same stop, engine
   exit from the next hourly bar. One preregistered holdout test (2017 to 2026):
   annualised monthly Sharpe difference versus base, quarter block bootstrap,
   one sided z 1.64.

Minute labels are checked against the hourly bars (open of the hour must equal
the open of its first minute) and the label convention is picked automatically.

Usage (repo folder):  python3 research_1m.py DATA_DIR DATA_DIR_1m [--symbols ...]
Writes research/1m_report.md and research/1m_trades.csv.
"""
import os, sys, csv, math, json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from statistics import NormalDist
import numpy as np

from research_exits import harvest, features, exit_engine, rolling_extreme, quarter, block_t
from research_model import featurize, TICK_FIX
from research_v3 import TierScorer, cls_of
from batch_backtest import build_catalog, iso, symbol_of
from backtest_hull import load_series
from instruments import TICKS
from ib_contracts import UNIVERSE

OUT = "research"
WARMUP_DAYS = 60
SPLIT_YEAR = 2017
BOOT_REPS, SEED = 400, 31
Z = NormalDist().inv_cdf(0.95)


def load_minutes(path, hours):
    """Minute bars whose hour (under both label conventions) is in `hours`.
    Returns dict hour_ts -> list of (ts, o, h, l, c) under convention END (label is
    the minute's end) and START (label is the minute's start)."""
    want = set(hours)
    end_conv, start_conv = defaultdict(list), defaultdict(list)
    with open(path) as f:
        for line in f:
            p = line.split(",")
            if len(p) < 5: continue
            try:
                ts = int(datetime.strptime(p[0][:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                continue
            h_start = ts - ts % 3600
            h_end = (ts - 60) - (ts - 60) % 3600
            if h_start in want or h_end in want:
                bar = (ts, float(p[1]), float(p[2]), float(p[3]), float(p[4]))
                if h_start in want: start_conv[h_start].append(bar)
                if h_end in want: end_conv[h_end].append(bar)
    return end_conv, start_conv


def main():
    args = sys.argv[1:]
    if len(args) < 2: sys.exit("usage: python3 research_1m.py DATA_DIR DATA_DIR_1m [--symbols ...]")
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(args[0]); tier = TierScorer()
    import glob, re
    cat1 = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p
            for p in glob.glob(os.path.join(args[1], "*_full_1min*"))}
    if not cat1: sys.exit(f"no *_full_1min* files in {args[1]}")
    os.makedirs(OUT, exist_ok=True)

    rows = []; align = defaultdict(int)
    for sym in syms:
        if sym not in cat or sym not in cat1 or sym not in tier.cheap: continue
        tick = TICK_FIX.get(sym, TICKS.get(sym, 0.0))
        T = load_series(cat[sym])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(cat[sym], start_ts=start_ts)
        D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
        D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        # v2 base trades, same replay as research_v3
        base, busy, taken = [], -1, set()
        for t in sorted(by_bar):
            if t < busy: continue
            for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                if sg["edge"] in taken: continue
                taken.add(sg["edge"])
                ei, ex, why, mfe = exit_engine(D, sg); busy = ei
                f = features(D, sg)
                row = dict(symbol=sym, dir=sg["dir"], touches=sg["touches"], span=sg["t0"] - sg["a"], hour=f["hour"],
                           dow=f["dow"], stop_src=sg["stop_src"], inst_cost=tier.inst_cost[sym],
                           **{k: f[k] for k in ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20",
                                                "p_ext_1y", "p_atr_ratio", "p_risk_atr"]})
                if tier.score(row) < tier.cutoff: break
                base.append((sg, ei, ex, f))
                break
        hours = [int(D["T"][sg["t0"]]) for sg, *_ in base]
        end_conv, start_conv = load_minutes(cat1[sym], hours)
        # pick the label convention whose first minute open matches the hourly open most often
        def match(conv):
            ok = 0
            for sg, *_ in base:
                ms = conv.get(int(D["T"][sg["t0"]]))
                if ms and abs(ms[0][1] - D["O"][sg["t0"]]) <= max(1e-9, 1e-6 * abs(D["O"][sg["t0"]])): ok += 1
            return ok
        me, msx = match(end_conv), match(start_conv)
        conv = end_conv if me >= msx else start_conv
        align[sym] = (max(me, msx), len(base), "END" if me >= msx else "START")

        for sg, ei, ex, f in base:
            t0, d = sg["t0"], sg["dir"]
            arr = D["L"] if d < 0 else D["H"]
            a, b, _ = sg["edge"]; m = (arr[b] - arr[a]) / (b - a)
            lt_raw = arr[a] + m * (t0 - a); lt2 = arr[sg["a"]] + sg["m2"] * (t0 - sg["a"])
            trigger = min(lt_raw, lt2) if d < 0 else max(lt_raw, lt2)
            ms = conv.get(int(D["T"][t0]), [])
            R1 = abs(sg["entry"] - sg["stop0"]); cost = 2.0 * tick / R1 if tick else 0.0
            rec = dict(symbol=sym, entry_time=iso(D["T"][t0]), entry_ts=int(D["T"][t0]), year=int(iso(D["T"][t0])[:4]),
                       quarter=quarter(D["T"][t0]), dir=d, minutes=len(ms), trigger=trigger, engine_entry=sg["entry"],
                       R=(ex - sg["entry"]) / R1 * d - cost, R_px=R1, tick=tick)
            # A. realistic stop fill
            fill_line = fill_mid = fill_worst = None; gap = False
            for i, (ts, o, h, l, c) in enumerate(ms):
                breached = (l <= trigger) if d < 0 else (h >= trigger)
                if not breached: continue
                if (d < 0 and o <= trigger) or (d > 0 and o >= trigger):
                    fill_line = fill_mid = fill_worst = o; gap = (i == 0)
                else:
                    ext = l if d < 0 else h
                    fill_line, fill_mid, fill_worst = trigger, (trigger + ext) / 2, ext
                break
            rec.update(gap=gap, breached=fill_line is not None)
            for name, fp in (("line", fill_line), ("mid", fill_mid), ("worst", fill_worst)):
                if fp is None:
                    rec[f"R_{name}"] = None; rec[f"slip_{name}_ticks"] = None; continue
                Rf = abs(fp - sg["stop0"])
                rec[f"R_{name}"] = ((ex - fp) / Rf * d - (2.0 * tick / Rf if tick else 0.0)) if Rf > 0 else None
                rec[f"slip_{name}_ticks"] = ((trigger - fp) * d / tick) if tick else None
            # B. 1 minute confirmation
            rec["R_conf"] = None; rec["conf_delay_min"] = None
            for i, (ts, o, h, l, c) in enumerate(ms):
                beyond = (c <= lt2) if d < 0 else (c >= lt2)
                if not beyond: continue
                fp = ms[i + 1][1] if i + 1 < len(ms) else c
                Rf = abs(fp - sg["stop0"])
                if Rf > 0:
                    s2 = dict(sg, entry=fp)
                    ei2, ex2, _, _ = exit_engine(D, s2)
                    rec["R_conf"] = (ex2 - fp) / Rf * d - (2.0 * tick / Rf if tick else 0.0)
                    rec["conf_delay_min"] = i + 1
                break
            rows.append(rec)
        print(f"{sym:5s} v2 trades {len(base)}, minute alignment {align[sym][0]}/{align[sym][1]} ({align[sym][2]})")

    with open(os.path.join(OUT, "1m_trades.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    def monthly(sel, key):
        ms = defaultdict(float)
        for r in sel:
            if r.get(key) is not None: ms[r["entry_time"][:7]] += r[key]
        return ms

    def sharpe_diff_t(sel, ka, kb):
        ma, mb = monthly(sel, ka), monthly(sel, kb); months = sorted(set(ma) | set(mb))
        by_q = defaultdict(list)
        for k in months: by_q[int(k[:4]) * 4 + (int(k[5:]) - 1) // 3].append(k)
        keys = list(by_q); rng = np.random.default_rng(SEED)
        def shp(ms, ks):
            v = np.array([ms.get(k, 0.0) for k in ks]); return v.mean() / v.std() * math.sqrt(12) if v.std() > 0 else 0.0
        diffs = []
        for _ in range(BOOT_REPS):
            pick = rng.integers(0, len(keys), len(keys)); ks = [k for i in pick for k in by_q[keys[i]]]
            diffs.append(shp(mb, ks) - shp(ma, ks))
        d = shp(mb, months) - shp(ma, months); sd = float(np.std(diffs))
        return d, (d / sd if sd > 0 else float("nan")), shp(ma, months), shp(mb, months)

    L = ["# 1 minute study on the v2 trade set\n",
         f"{len(rows)} v2 trades across {len(align)} instruments with 1 minute data. Minute alignment (first minute "
         f"open equals hourly open): {sum(a[0] for a in align.values())}/{sum(a[1] for a in align.values())}.\n"]
    breached = [r for r in rows if r["breached"]]
    L.append("## A. Fill realism for resting stop orders (calibration)\n")
    L.append(f"Trades whose entry hour's minutes breach the order level: {len(breached)} of {len(rows)} "
             f"({len(breached) / max(1, len(rows)):.0%}); first minute already past the level (gap fill): "
             f"{sum(1 for r in breached if r['gap'])}.\n")
    L.append("| fill assumption | avgR (all periods) | avgR 2017 to 2026 | median slippage vs line (ticks) | mean slippage (ticks) |")
    L.append("|---|---|---|---|---|")
    hb = [r for r in breached if r["year"] >= SPLIT_YEAR]
    for name in ("line", "mid", "worst"):
        rs = [r[f"R_{name}"] for r in breached if r[f"R_{name}"] is not None]
        rh = [r[f"R_{name}"] for r in hb if r[f"R_{name}"] is not None]
        sl = [r[f"slip_{name}_ticks"] for r in breached if r[f"slip_{name}_ticks"] is not None]
        L.append(f"| {name} | {np.mean(rs):+.4f} | {np.mean(rh):+.4f} | {np.median(sl):+.1f} | {np.mean(sl):+.1f} |")
    L.append(f"| engine (backtest) | {np.mean([r['R'] for r in breached]):+.4f} | {np.mean([r['R'] for r in hb]):+.4f} | 0 (minus 2 ticks per round trip in all rows) | |")
    L.append("\nRead: `mid` is the honest expectation for a stop order; `worst` is a floor. The difference between "
             "`line` and `mid` is the slippage the backtest's 2 tick assumption has to cover.\n")

    L.append("## B. 1 minute confirmation entry (one preregistered test)\n")
    expl = [r for r in rows if r["year"] < SPLIT_YEAR]; hold = [r for r in rows if r["year"] >= SPLIT_YEAR]
    for label, sel in (("exploration 2008 to 2016", expl), ("holdout 2017 to 2026", hold)):
        conf = [r for r in sel if r["R_conf"] is not None]
        d, t, sa, sb = sharpe_diff_t(sel, "R", "R_conf")
        verdict = ("PASS" if t > Z else "no") if label.startswith("holdout") else "(exploration)"
        L.append(f"- {label}: {len(conf)} of {len(sel)} confirmed on 1 minute, avgR {np.mean([r['R_conf'] for r in conf]) if conf else 0:+.4f} "
                 f"vs base {np.mean([r['R'] for r in sel]):+.4f}; median delay {np.median([r['conf_delay_min'] for r in conf]) if conf else 0:.0f} min; "
                 f"Sharpe {sa:.2f} -> {sb:.2f}, diff {d:+.2f}, t {t:.2f} **{verdict}**")
    open(os.path.join(OUT, "1m_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/1m_report.md, {OUT}/1m_trades.csv")


if __name__ == "__main__":
    main()
