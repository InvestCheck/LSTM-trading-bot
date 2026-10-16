#!/usr/bin/env python3
"""Backtest portfolio stats for v1, cost cap only, and v2 (cost cap + frozen tier cut).

Engine fills at the line, 2 ticks per round trip, NO commissions, one position
per instrument, R accounting (every trade risks 1R). The 2017 to 2026 rows are
the honest ones for v2: the tier model was fit on 2008 to 2016.

Usage (repo folder):  python3 stats_v2.py
Needs research/intrabar/signals.csv (with p_* columns), research/tier_model.json,
v2_config.json.
"""
import csv, json, math
from collections import defaultdict
import numpy as np
from research_model import featurize, TICK_FIX

m = json.load(open("research/tier_model.json"))
cfg = json.load(open("v2_config.json"))
mu, sd = np.array(m["mu"]), np.array(m["sd"])
lo, hi, w = np.array(m["clip_lo"]), np.array(m["clip_hi"]), np.array(m["weights"])
cheap, inst_cost = set(cfg["cheap"]), cfg["inst_cost"]

rows = []
for r in csv.DictReader(open("research/intrabar/signals.csv")):
    if r["why_engine"] == "skipped": continue
    g, n = float(r["gross_engine"]), float(r["R_engine"])
    rpx = abs(float(r["entry"]) - float(r["stop0"]))
    if r["symbol"] in TICK_FIX and rpx > 0: n = g - 2 * TICK_FIX[r["symbol"]] / rpx
    d = dict(symbol=r["symbol"], dir=int(r["dir"]), touches=int(r["touches"]), span=int(r["span"]),
             hour=int(r["hour"]), dow=int(r["dow"]), stop_src=r["stop_src"],
             inst_cost=inst_cost.get(r["symbol"], 0.1),
             **{k: float(r[k]) for k in ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20",
                                         "p_ext_1y", "p_atr_ratio", "p_risk_atr"]})
    x = np.array(featurize(d), float); x[~np.isfinite(x)] = 0.0
    z = np.clip((np.clip(x, lo, hi) - mu) / sd, -m.get("z_clip", 5.0), m.get("z_clip", 5.0))
    score = float(m["intercept"] + z @ w)
    rows.append(dict(t=r["entry_time"], s=r["symbol"], n=n, cheap=r["symbol"] in cheap, top=score >= m["cutoff"]))
rows.sort(key=lambda r: r["t"])


def stats(sel, label):
    if not sel: print(f"{label}: no trades"); return
    R = np.array([x["n"] for x in sel])
    months = defaultdict(float); years = defaultdict(float)
    for x in sel: months[x["t"][:7]] += x["n"]; years[x["t"][:4]] += x["n"]
    y, mo = map(int, sel[0]["t"][:7].split("-")); y1, m1 = map(int, sel[-1]["t"][:7].split("-"))
    keys = []
    while (y, mo) <= (y1, m1):
        keys.append(f"{y:04d}-{mo:02d}"); mo += 1
        if mo > 12: y, mo = y + 1, 1
    mv = np.array([months.get(k, 0.0) for k in keys]); yrs = len(keys) / 12
    eq = np.cumsum(R); dd = np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq
    eps, cur = [], 0.0
    for v in dd:
        if v > 0: cur = max(cur, v)
        elif cur > 0: eps.append(cur); cur = 0.0
    if cur > 0: eps.append(cur)
    big = [e for e in eps if e >= 5]
    print(f"{label}: {len(R)} trades ({len(R) / yrs:.0f}/yr), avgR {R.mean():+.4f}, {R.sum() / yrs:+.1f} R/yr")
    print(f"   Sharpe (monthly, annualised) {mv.mean() / mv.std() * math.sqrt(12):.2f}, losing months "
          f"{np.mean(mv < 0) * 100:.0f}%, worst month {mv.min():+.1f}R, worst year {min(years.values()):+.1f}R")
    print(f"   max drawdown {dd.max():.1f}R, median of drawdowns >= 5R: {np.median(big) if big else 0:.1f}R "
          f"({len(big)} of them)")
    print("   by year: " + " ".join(f"{k}:{v:+.0f}" for k, v in sorted(years.items())))


for period, cond in [("2017-2026 (honest for v2)", lambda r: r["t"][:4] >= "2017"), ("2008-2026", lambda r: True)]:
    print(f"\n=== {period} ===")
    p = [r for r in rows if cond(r)]
    stats(p, "v1 (every signal)")
    stats([r for r in p if r["cheap"]], "cost cap only")
    stats([r for r in p if r["cheap"] and r["top"]], "v2 (cost cap + tier cut)")
