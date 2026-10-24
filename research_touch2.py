#!/usr/bin/env python3
"""Two touch lines: does lowering the minimum touches from 3 to 2 add trades
without lowering the R per trade?

Harvests the engine's entries twice (MINTOUCH 3 = the frozen engine, MINTOUCH 2),
sequences each the engine's way (one position per instrument), scores every
trade with the engine exit, and applies the v2 gate as the live bot does (cheap
instrument, frozen tier score >= cutoff from research/tier_model.json). The tier
model was fitted on 3 touch trades, so on 2 touch trades it is an extrapolation;
the report shows both with and without the gate.

Preregistered test (holdout 2017 to 2026, v2 gated): the trades the 2 touch
engine takes that are 2 touch lines have avgR > 0 with quarter block t > 1.64,
AND the 2 touch engine's total R per year exceeds the 3 touch engine's. Both
must already hold on 2008 to 2016 or the holdout is not read for this.

Usage (repo folder):  python3 research_touch2.py DATA_DIR [--symbols GC ES ...]
Writes research/touch2_report.md and research/touch2_trades.csv.
"""
import os, sys, csv, json, math
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import load_series
from batch_backtest import build_catalog, iso
from instruments import TICKS
from ib_contracts import UNIVERSE
from research_exits import harvest, exit_engine, features, rolling_extreme, quarter, block_t, summarize, WARMUP_DAYS
from tier import CLASSES, NAMES

OUT = "research"; Z = 1.64; SPLIT = 2017


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(args[0]); cfg = json.load(open("v2_config.json")); cheap = set(cfg["cheap"]); inst_cost = cfg["inst_cost"]
    m = json.load(open(os.path.join(OUT, "tier_model.json"))); assert m["names"] == NAMES
    mu, sd, lo, hi, w = (np.array(m[k]) for k in ("mu", "sd", "clip_lo", "clip_hi", "weights")); b, cut = m["intercept"], m["cutoff"]
    def tier_score(sym, sg, f):
        dt = datetime.fromtimestamp(int(sg["ts"]), timezone.utc); cls = next((c for c, l in CLASSES.items() if sym in l), "OTHER")
        x = [f[k] for k in NAMES[:9]] + [math.log(max(1, sg["span"])), sg["touches"], 1.0 if sg["dir"] > 0 else 0.0, 1.0 if sg["stop_src"] == "ema" else 0.0,
             math.sin(2 * math.pi * dt.hour / 24), math.cos(2 * math.pi * dt.hour / 24), 1.0 if dt.weekday() == 6 else 0.0, inst_cost.get(sym, 0.1)] + [1.0 if cls == c else 0.0 for c in CLASSES]
        x = np.array(x, float); x[~np.isfinite(x)] = 0; z = np.clip((np.clip(x, lo, hi) - mu) / sd, -5, 5); return float(b + z @ w)

    rows = []
    for s in syms:
        if s not in cat: print(f"{s:5s} missing"); continue
        tick = TICKS.get(s, 0.0); T = load_series(cat[s])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        for mt in (3, 2):
            D, sigs = harvest(cat[s], start_ts=start_ts, fill="intrabar", MINTOUCH=mt)
            days = (D["T"] // 86400).astype(int); Cb = D["C"]; nb = len(Cb)
            D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
            D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
            by_bar = defaultdict(list)
            for sg in sigs: by_bar[sg["t0"]].append(sg)
            busy, taken = -1, set()
            for t in sorted(by_bar):
                if t < busy: continue
                for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                    if sg["edge"] in taken: continue
                    taken.add(sg["edge"]); ei, ex, why, _ = exit_engine(D, sg); R = abs(sg["entry"] - sg["stop0"])
                    r = (ex - sg["entry"]) / R * sg["dir"] - ((2.0 * tick) / R if tick else 0.0)
                    sg["ts"] = int(D["T"][t]); sg["span"] = t - sg["a"]; f = features(D, sg); sc = tier_score(s, sg, f)
                    t1 = min(int(ei), nb - 1); mark = sg["entry"]; path = []; cost = (2.0 * tick) / R if tick else 0.0
                    for k in range(t, t1 + 1):
                        if k == t1 or days[k + 1] != days[k]:
                            px = ex if k == t1 else Cb[k]; path.append((int(days[k]), sg["dir"] * (px - mark) / R)); mark = px
                    if path: path[-1] = (path[-1][0], path[-1][1] - cost)
                    rows.append(dict(symbol=s, engine=mt, entry_time=iso(D["T"][t]), year=datetime.fromtimestamp(int(D["T"][t]), timezone.utc).year, quarter=quarter(D["T"][t]),
                                     dir=sg["dir"], touches=sg["touches"], span=sg["span"], score=round(sc, 4), v2=int(s in cheap and sc >= cut), R=round(r, 6), why=why,
                                     entry=sg["entry"], stop0=sg["stop0"], t0=t, exit_idx=t1, cls=next((c for c, l in CLASSES.items() if s in l), "OTHER"), path=path))
                    busy = ei; break
        n3 = sum(1 for r in rows if r["symbol"] == s and r["engine"] == 3); n2 = sum(1 for r in rows if r["symbol"] == s and r["engine"] == 2)
        print(f"{s:5s} 3 touch {n3:5d} trades, 2 touch {n2:5d} ({sum(1 for r in rows if r['symbol'] == s and r['engine'] == 2 and r['touches'] == 2)} are 2 touch lines)", flush=True)
    with open(os.path.join(OUT, "touch2_trades.csv"), "w", newline="") as fh:
        cols = [k for k in rows[0] if k != "path"]; wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); wr.writeheader(); wr.writerows(rows)

    yrs = {p: (SPLIT - 2008 if p == "explore" else 2026.8 - SPLIT) for p in ("explore", "holdout")}
    L = ["# Two touch lines vs the frozen three touch engine\n",
         "Each engine sequenced on its own (one position per instrument). v2 = cheap instrument and frozen tier score >= cutoff. "
         "'2 touch only' = trades the 2 touch engine took on lines with exactly 2 touches.\n",
         "| set | gate | engine | trades | trades/yr | avgR | win% | total R/yr | boot t |", "|---|---|---|---|---|---|---|---|---|"]
    gate_ok = {}
    for pname, cond in (("explore", lambda r: r["year"] < SPLIT), ("holdout", lambda r: r["year"] >= SPLIT)):
        for gname, g in (("all", lambda r: True), ("v2", lambda r: r["v2"] == 1)):
            for ename, e in (("3 touch", lambda r: r["engine"] == 3), ("2 touch", lambda r: r["engine"] == 2), ("2 touch only", lambda r: r["engine"] == 2 and r["touches"] == 2)):
                sub = [r for r in rows if cond(r) and g(r) and e(r)]
                if not sub: continue
                sm = summarize([r["R"] for r in sub]); _, t = block_t([r["R"] for r in sub], [r["quarter"] for r in sub])
                L.append(f"| {pname} | {gname} | {ename} | {sm['n']} | {sm['n'] / yrs[pname]:.0f} | {sm['avgR']:+.4f} | {sm['win']:.0f} | {sm['totalR'] / yrs[pname]:+.1f} | {t:.2f} |")
                if gname == "v2": gate_ok[(pname, ename)] = (sm["avgR"], t, sm["totalR"] / yrs[pname])
    def verdict(p):
        a = gate_ok.get((p, "2 touch only")); e2 = gate_ok.get((p, "2 touch")); e3 = gate_ok.get((p, "3 touch"))
        if not (a and e2 and e3): return "not enough trades", False
        ok = a[0] > 0 and a[1] > Z and e2[2] > e3[2]
        return f"2 touch only avgR {a[0]:+.4f} t {a[1]:.2f}; total R/yr 2 touch {e2[2]:+.1f} vs 3 touch {e3[2]:+.1f} -> {'PASS' if ok else 'no'}", ok
    ve, oke = verdict("explore"); vh, okh = verdict("holdout")
    L += ["\n## Preregistered test (v2 gated)\n", f"Exploration: {ve}", f"Holdout: {vh}" if oke else f"Holdout: not read for the decision (exploration failed); for the record: {vh}",
          "\nCaveat: the tier model has never seen a 2 touch line; its touches weight is extrapolated. If 2 touch trades are positive ungated "
          "but the gate removes them, the right follow up is a refit with 2 touch trades in the fit, not a conclusion."]
    # ---- risk: daily mark to market of each v2 gated book, one unit of risk per trade
    def book(eng):
        daily = defaultdict(float); open_by_day = defaultdict(int); cl_by_day = defaultdict(lambda: defaultdict(int))
        for r in rows:
            if r["engine"] != eng or not r["v2"] or not r["path"]: continue
            for dd, v in r["path"]: daily[dd] += v; open_by_day[dd] += 1; cl_by_day[dd][r["cls"]] += 1
        ds = np.array(sorted(daily)); pnl = np.array([daily[d] for d in ds]); yr = np.array([datetime.fromtimestamp(d * 86400, timezone.utc).year for d in ds])
        conc = np.array([open_by_day[d] for d in ds]); clmax = np.array([max(cl_by_day[d].values()) for d in ds])
        return ds, pnl, yr, conc, clmax
    def sharpe(x): return float(x.mean() / x.std() * math.sqrt(252)) if len(x) > 20 and x.std() > 0 else float("nan")
    def maxdd(x):
        c = np.cumsum(x); return float(np.max(np.maximum.accumulate(c) - c)) if len(c) else 0.0
    L += ["\n## Risk of the v2 gated books (daily mark to market, one unit of risk per trade)\n",
          "| set | engine | Sharpe | max DD (R) | total R | daily vol (R) | open positions median / max | same cluster max | total R at the 3 touch book's vol |", "|---|---|---|---|---|---|---|---|---|"]
    b3 = book(3); b2 = book(2)
    for pname, cond in (("explore", lambda y: y < SPLIT), ("holdout", lambda y: y >= SPLIT)):
        m3 = cond(b3[2]); ref_vol = b3[1][m3].std()
        for ename, bk in (("3 touch", b3), ("2 touch", b2)):
            ds, pnl, yr, conc, clmax = bk; mm = cond(yr); x = pnl[mm]
            L.append(f"| {pname} | {ename} | {sharpe(x):.2f} | {maxdd(x):.1f} | {x.sum():+.0f} | {x.std():.2f} | {int(np.median(conc[mm]))} / {int(conc[mm].max())} | {int(clmax[mm].max())} | {x.sum() * ref_vol / x.std():+.0f} |")
    L += ["\n| year | 3 touch total R | 2 touch total R | 3 touch max DD | 2 touch max DD |", "|---|---|---|---|---|"]
    for y in sorted(set(b3[2])):
        x3 = b3[1][b3[2] == y]; x2 = b2[1][b2[2] == y]
        L.append(f"| {y} | {x3.sum():+.0f} | {x2.sum():+.0f} | {maxdd(x3):.0f} | {maxdd(x2):.0f} |")
    L.append("\nThe last column scales the 2 touch book down to the 3 touch book's daily volatility: the fair comparison when risk per trade is set by a total risk budget rather than fixed per trade.")
    # ---- correlation with the S&P 500 (ES continuous, daily and monthly), and the books in ES's worst months
    if "ES" in cat:
        Te, _, _, _, Ce = load_series(cat["ES"]); de = (Te // 86400).astype(int); last = {}
        for d_, c_ in zip(de, Ce): last[int(d_)] = float(c_)
        dd = np.array(sorted(last)); px = np.array([last[d_] for d_ in dd]); ret = np.diff(px) / np.maximum(px[:-1], 1e-9); es_day = dict(zip(dd[1:], ret))
        L += ["\n## Correlation with the S&P 500 (ES continuous contract returns)\n",
              "| set | engine | daily corr | monthly corr | book R in ES's worst 10% months (avg per month) | book R in the other months | ES up months corr | ES down months corr |", "|---|---|---|---|---|---|---|---|"]
        for pname, cond in (("explore", lambda y: y < SPLIT), ("holdout", lambda y: y >= SPLIT)):
            for ename, bk in (("3 touch", b3), ("2 touch", b2)):
                ds, pnl, yr, _, _ = bk; mm = cond(yr); ds_, pnl_ = ds[mm], pnl[mm]
                e = np.array([es_day.get(int(d_), np.nan) for d_ in ds_]); ok = ~np.isnan(e)
                cd = float(np.corrcoef(pnl_[ok], e[ok])[0, 1]) if ok.sum() > 30 else float("nan")
                mo = defaultdict(float); me = defaultdict(float)
                for d_, v, ev in zip(ds_, pnl_, e):
                    k = datetime.fromtimestamp(int(d_) * 86400, timezone.utc).strftime("%Y-%m"); mo[k] += v
                    if not np.isnan(ev): me[k] += ev
                keys = sorted(k for k in mo if k in me); bm = np.array([mo[k] for k in keys]); em = np.array([me[k] for k in keys])
                cm = float(np.corrcoef(bm, em)[0, 1]) if len(keys) > 12 else float("nan")
                q = np.quantile(em, 0.1); worst = em <= q; up = em > 0
                cu = float(np.corrcoef(bm[up], em[up])[0, 1]) if up.sum() > 12 else float("nan"); cdn = float(np.corrcoef(bm[~up], em[~up])[0, 1]) if (~up).sum() > 12 else float("nan")
                L.append(f"| {pname} | {ename} | {cd:+.2f} | {cm:+.2f} | {bm[worst].mean():+.1f} (n={worst.sum()}) | {bm[~worst].mean():+.1f} | {cu:+.2f} | {cdn:+.2f} |")
        L += ["\n| year | ES return (approx) | 3 touch R | 2 touch R | 3 touch daily corr | 2 touch daily corr |", "|---|---|---|---|---|---|"]
        for y in sorted(set(b3[2])):
            cells = []; esr = float(np.nansum([es_day.get(int(d_), np.nan) for d_ in b3[0][b3[2] == y]]))
            for bk in (b3, b2):
                ds_, pnl_ = bk[0][bk[2] == y], bk[1][bk[2] == y]; e = np.array([es_day.get(int(d_), np.nan) for d_ in ds_]); ok = ~np.isnan(e)
                cells.append(f"{np.corrcoef(pnl_[ok], e[ok])[0, 1]:+.2f}" if ok.sum() > 30 else "n/a")
            L.append(f"| {y} | {esr * 100:+.0f}% | {b3[1][b3[2] == y].sum():+.0f} | {b2[1][b2[2] == y].sum():+.0f} | {cells[0]} | {cells[1]} |")
        L.append("\nES returns are on the back adjusted continuous series, so the level is approximate but the sign and ranking of months are right. "
                 "A near zero correlation with a positive number in ES's worst months is the diversifying shape; a positive correlation means the book falls with stocks.")
    open(os.path.join(OUT, "touch2_report.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}/touch2_report.md")


if __name__ == "__main__":
    main()
