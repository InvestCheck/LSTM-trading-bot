#!/usr/bin/env python3
"""v3 candidates on top of protocol v2, explored on 2008 to 2016, tested once on
2017 to 2026.

Base set: v2 = the engine's trades on instruments passing the cost cap, with a
frozen tier score at or above the cutoff (v2_config.json, research/tier_model.json).

Candidates (each applied to the base set):
  stop_rule     skip trades whose initial stop is more than 2.5 ATR away
  session       skip trades entered outside 08:00 to 16:59 ET
  chandelier    exit with a 3 ATR chandelier trail instead of the engine's exit
  retest        enter only on a return to the broken line within 24 bars (fill at
                the line, same stop); skip the trade if no retest or stopped first
  pyramid       add a second unit on a later same direction break while the first
                trade is past 1R; second unit has its own stop, exits with the first
  sizing        1.5 units on the top quartile of tier score, 1 unit otherwise
  cluster_cap   at most 3 concurrent trades per asset class (portfolio level)

Preregistered holdout tests (one sided, Bonferroni over N_TESTS):
  filters (stop_rule, session, cluster_cap): avgR in minus out, quarter block bootstrap
  chandelier: paired avgR difference versus the engine exit
  retest, pyramid, sizing: annualised monthly Sharpe difference versus base,
    quarter block bootstrap (these change the portfolio, not single trades)
  combo_A: stop_rule + chandelier
  combo_B: every candidate whose exploration half effect is positive, fixed by
    the script before the holdout is read

Costs: 2 ticks per round trip. 1 minute confirmation is not here (needs the
1 minute data pipeline).

Usage (repo folder):  python3 research_v3.py DATA_DIR [--symbols ...]
Writes research/v3_report.md and research/v3_trades.csv.
"""
import os, sys, csv, math, json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from statistics import NormalDist
import numpy as np

from research_exits import harvest, features, exit_engine, exit_chandelier, rolling_extreme, quarter, block_t
from research_model import featurize, TICK_FIX
from batch_backtest import build_catalog, iso
from backtest_hull import load_series
from instruments import TICKS
from ib_contracts import UNIVERSE

OUT = "research"
WARMUP_DAYS = 60
SPLIT_YEAR = 2017
BOOT_REPS, SEED = 400, 21
RETEST_BARS, RETEST_BAND = 24, 0.25
STOP_MAX_ATR = 2.5
SESSION = (8, 16)
CLUSTER_CAP = 3
SIZE_TOP = 1.5
CLASSES = {
    "FX": "A6 AD B6 CNH E1 E6 E7 J1 J7 MP N6 NOK SEK RP RY SIR DX".split(),
    "EQ": "ES NQ RTY EW NIY NKD YM FDAX FDXM FESX FXXP FCE FTI FTUK MFS MME".split(),
    "RATES": "ZT ZF ZN TN UB FGBL FGBM FGBX FOAT FBTP FBON G".split(),
    "ENERGY": "CL BZ B HO RB NG".split(),
    "METALS": "GC MGC SI HG PA PL".split(),
    "AGS": "ZC XC ZS ZL ZM KE CT SB RS DC GF HE LE".split(),
}
CANDIDATES = ["stop_rule", "session", "chandelier", "retest", "pyramid", "sizing", "cluster_cap"]
N_TESTS = len(CANDIDATES) + 2
Z = NormalDist().inv_cdf(1 - 0.05 / N_TESTS)


def cls_of(sym):
    return next((c for c, lst in CLASSES.items() if sym in lst), "OTHER")


class TierScorer:
    def __init__(self):
        m = json.load(open("research/tier_model.json")); cfg = json.load(open("v2_config.json"))
        self.mu, self.sd = np.array(m["mu"]), np.array(m["sd"])
        self.lo, self.hi, self.w = np.array(m["clip_lo"]), np.array(m["clip_hi"]), np.array(m["weights"])
        self.b, self.cutoff, self.zc = m["intercept"], m["cutoff"], m.get("z_clip", 5.0)
        self.cheap, self.inst_cost = set(cfg["cheap"]), cfg["inst_cost"]

    def score(self, row):
        x = np.array(featurize(row), float); x[~np.isfinite(x)] = 0.0
        z = np.clip((np.clip(x, self.lo, self.hi) - self.mu) / self.sd, -self.zc, self.zc)
        return float(self.b + z @ self.w)


def retest_entry(D, s):
    """Return (t_entry, fill) if price comes back to the broken line within
    RETEST_BARS bars before hitting the stop, else None."""
    O, H, L, A = D["O"], D["H"], D["L"], D["A"]
    t0, d, stp, a2, m2 = s["t0"], s["dir"], s["stop0"], s["a"], s["m2"]
    arr = L if d < 0 else H
    for t in range(t0 + 1, min(len(O), t0 + RETEST_BARS + 1)):
        lt = arr[a2] + m2 * (t - a2)
        band = RETEST_BAND * A[t]
        if d < 0:
            if H[t] >= stp: return None
            if H[t] >= lt - band: return t, float(min(H[t], lt))
        else:
            if L[t] <= stp: return None
            if L[t] <= lt + band: return t, float(max(L[t], lt))
    return None


def pyramid_add(D, s, exit_idx, exit_px, by_bar, R1):
    """First same direction candidate after the trade is 1R in profit; its own
    stop, exits with the first trade. Returns the add's R (per unit) or None."""
    H, L = D["H"], D["L"]
    t0, d, entry = s["t0"], s["dir"], s["entry"]
    mfe = 0.0
    for t in range(t0 + 1, exit_idx):
        mfe = max(mfe, d * ((H[t] if d > 0 else L[t]) - entry) / R1)
        if mfe < 1.0: continue
        for c in by_bar.get(t, []):
            if c["dir"] != d: continue
            e2, s2 = c["entry"], c["stop0"]; R2 = abs(e2 - s2)
            if R2 <= 0: continue
            for u in range(t + 1, exit_idx + 1):
                if (d < 0 and H[u] >= s2) or (d > 0 and L[u] <= s2):
                    return -1.0
            return (exit_px - e2) / R2 * d
    return None


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_v3.py DATA_DIR [--symbols ...]")
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(args[0]); tier = TierScorer()
    os.makedirs(OUT, exist_ok=True)
    print(f"{N_TESTS} preregistered holdout tests, one sided z {Z:.2f}")

    trades = []
    for sym in syms:
        if sym not in cat or sym not in tier.cheap: continue
        tick = TICKS.get(sym, 0.0); tick = TICK_FIX.get(sym, tick)
        T = load_series(cat[sym])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(cat[sym], start_ts=start_ts)
        D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
        D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        busy, taken, n_base = -1, set(), 0
        for t in sorted(by_bar):
            if t < busy: continue
            for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                if sg["edge"] in taken: continue
                taken.add(sg["edge"])
                ei, ex, why, mfe = exit_engine(D, sg)
                busy = ei
                R1 = abs(sg["entry"] - sg["stop0"]); cost = 2.0 * tick / R1 if tick else 0.0
                f = features(D, sg)
                row = dict(symbol=sym, dir=sg["dir"], touches=sg["touches"], span=sg["t0"] - sg["a"],
                           hour=f["hour"], dow=f["dow"], stop_src=sg["stop_src"], inst_cost=tier.inst_cost[sym],
                           **{k: f[k] for k in ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20",
                                                "p_ext_1y", "p_atr_ratio", "p_risk_atr"]})
                score = tier.score(row)
                if score < tier.cutoff: break                  # not in v2: engine still holds it, but we do not trade it
                n_base += 1
                tr = dict(symbol=sym, cls=cls_of(sym), entry_time=iso(D["T"][sg["t0"]]), entry_ts=int(D["T"][sg["t0"]]),
                          exit_ts=int(D["T"][ei]), year=int(iso(D["T"][sg["t0"]])[:4]), quarter=quarter(D["T"][sg["t0"]]),
                          dir=sg["dir"], score=score, risk_atr=f["risk_atr"], hour=f["hour"],
                          R=(ex - sg["entry"]) / R1 * sg["dir"] - cost)
                ci, cx, _, _ = exit_chandelier(D, sg, 3.0)
                tr["R_chand"] = (cx - sg["entry"]) / R1 * sg["dir"] - cost
                rt = retest_entry(D, sg)
                if rt:
                    t2, fill = rt
                    s2 = dict(sg, t0=t2, entry=fill)
                    ei2, ex2, _, _ = exit_engine(D, s2)
                    R2 = abs(fill - sg["stop0"])
                    tr["R_retest"] = ((ex2 - fill) / R2 * sg["dir"] - (2.0 * tick / R2 if tick else 0.0)) if R2 > 0 else None
                    tr["retest_exit_ts"] = int(D["T"][ei2])
                else:
                    tr["R_retest"] = None
                add = pyramid_add(D, sg, ei, ex, by_bar, R1)
                tr["R_add"] = (add - cost) if add is not None else None
                trades.append(tr)
                break
        print(f"{sym:5s} v2 trades {n_base}")

    trades.sort(key=lambda x: x["entry_ts"])
    with open(os.path.join(OUT, "v3_trades.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trades[0].keys())); w.writeheader(); w.writerows(trades)

    # ---- portfolio helpers --------------------------------------------------
    def monthly(sel, key="R", weight=None, exit_key="exit_ts"):
        ms = defaultdict(float)
        for r in sel:
            v = r.get(key)
            if v is None: continue
            ms[iso(r["entry_ts"])[:7]] += v * (weight(r) if weight else 1.0)
        return ms

    def sharpe(ms, years):
        y0, m0 = map(int, min(ms).split("-")); y1, m1 = map(int, max(ms).split("-")); keys = []
        y, m = y0, m0
        while (y, m) <= (y1, m1):
            keys.append(f"{y:04d}-{m:02d}"); m += 1
            if m > 12: y, m = y + 1, 1
        v = np.array([ms.get(k, 0.0) for k in keys])
        return float(v.mean() / v.std() * math.sqrt(12)) if v.std() > 0 else float("nan")

    def sharpe_diff_t(sel, make_a, make_b):
        """Sharpe(b) - Sharpe(a) with a quarter block bootstrap over months."""
        ma, mb = make_a(sel), make_b(sel)
        months = sorted(set(ma) | set(mb))
        by_q = defaultdict(list)
        for k in months: by_q[(int(k[:4]) * 4 + (int(k[5:]) - 1) // 3)].append(k)
        keys = list(by_q); rng = np.random.default_rng(SEED); diffs = []
        def shp(ms, ks):
            v = np.array([ms.get(k, 0.0) for k in ks]); return v.mean() / v.std() * math.sqrt(12) if v.std() > 0 else 0.0
        for _ in range(BOOT_REPS):
            pick = rng.integers(0, len(keys), len(keys)); ks = [k for i in pick for k in by_q[keys[i]]]
            diffs.append(shp(mb, ks) - shp(ma, ks))
        d = shp(mb, months) - shp(ma, months); sd = float(np.std(diffs))
        return d, (d / sd if sd > 0 else float("nan")), shp(ma, months), shp(mb, months)

    def cluster_capped(sel):
        open_ = []; keep = []
        for r in sorted(sel, key=lambda x: x["entry_ts"]):
            open_ = [o for o in open_ if o[0] > r["entry_ts"]]
            if sum(1 for o in open_ if o[1] == r["cls"]) >= CLUSTER_CAP:
                keep.append(False); continue
            open_.append((r["exit_ts"], r["cls"])); keep.append(True)
        return keep

    def evaluate(sel, label, q75):
        """Returns dict name -> (effect, t, description)."""
        out = {}
        yrs = max(1e-9, (max(r["entry_ts"] for r in sel) - min(r["entry_ts"] for r in sel)) / (365.25 * 86400))
        base = [r["R"] for r in sel]; qs = [r["quarter"] for r in sel]
        bm, bt = block_t(base, qs)
        out["base"] = (bm, bt, f"{len(sel)} trades, {len(sel) / yrs:.0f}/yr, avgR {bm:+.4f}, {sum(base) / yrs:+.1f} R/yr, "
                               f"Sharpe {sharpe(monthly(sel), yrs):.2f}")
        for name, keep in (("stop_rule", lambda r: r["risk_atr"] <= STOP_MAX_ATR),
                           ("session", lambda r: SESSION[0] <= r["hour"] <= SESSION[1])):
            inn = [r for r in sel if keep(r)]; out_ = [r for r in sel if not keep(r)]
            by_q = defaultdict(list)
            for r in sel: by_q[r["quarter"]].append((r["R"], keep(r)))
            keys = list(by_q); rng = np.random.default_rng(SEED); diffs = []
            for _ in range(BOOT_REPS):
                pick = rng.integers(0, len(keys), len(keys))
                a = [v for i in pick for v, k in by_q[keys[i]] if k]; b = [v for i in pick for v, k in by_q[keys[i]] if not k]
                if a and b: diffs.append(np.mean(a) - np.mean(b))
            d = (np.mean([r["R"] for r in inn]) if inn else 0) - (np.mean([r["R"] for r in out_]) if out_ else 0)
            sd = float(np.std(diffs)) if diffs else float("nan")
            out[name] = (d, d / sd if sd and sd > 0 else float("nan"),
                         f"in {len(inn)} at {np.mean([r['R'] for r in inn]) if inn else 0:+.4f}, out {len(out_)} at "
                         f"{np.mean([r['R'] for r in out_]) if out_ else 0:+.4f}; in only: {sum(r['R'] for r in inn) / yrs:+.1f} R/yr")
        dm, dt = block_t([r["R_chand"] - r["R"] for r in sel], qs)
        out["chandelier"] = (dm, dt, f"paired diff {dm:+.4f} on {len(sel)}; Sharpe {sharpe(monthly(sel, 'R_chand'), yrs):.2f}")
        rt = [r for r in sel if r["R_retest"] is not None]
        d, t, sa, sb = sharpe_diff_t(sel, lambda s_: monthly(s_), lambda s_: monthly(s_, "R_retest"))
        out["retest"] = (d, t, f"{len(rt)} of {len(sel)} retested, avgR {np.mean([r['R_retest'] for r in rt]) if rt else 0:+.4f}, "
                               f"{sum(r['R_retest'] for r in rt) / yrs:+.1f} R/yr; Sharpe {sa:.2f} -> {sb:.2f}")
        def pyr_month(s_):
            ms = defaultdict(float)
            for r in s_:
                units = 2 if r["R_add"] is not None else 1
                ms[iso(r["entry_ts"])[:7]] += (r["R"] + (r["R_add"] or 0.0)) / units       # per unit of risk
            return ms
        d, t, sa, sb = sharpe_diff_t(sel, lambda s_: monthly(s_), pyr_month)
        adds = [r for r in sel if r["R_add"] is not None]
        out["pyramid"] = (d, t, f"{len(adds)} adds, add avgR {np.mean([r['R_add'] for r in adds]) if adds else 0:+.4f}; "
                                f"Sharpe per unit {sa:.2f} -> {sb:.2f}")
        wt = lambda r: SIZE_TOP if r["score"] >= q75 else 1.0
        d, t, sa, sb = sharpe_diff_t(sel, lambda s_: monthly(s_), lambda s_: monthly(s_, weight=wt))
        out["sizing"] = (d, t, f"top quartile x{SIZE_TOP}; Sharpe {sa:.2f} -> {sb:.2f}")
        keep = cluster_capped(sel); inn = [r for r, k in zip(sel, keep) if k]; out_ = [r for r, k in zip(sel, keep) if not k]
        d, t, sa, sb = sharpe_diff_t(sel, lambda s_: monthly(s_), lambda s_: monthly([r for r, k in zip(s_, cluster_capped(s_)) if k]))
        out["cluster_cap"] = (d, t, f"skips {len(out_)} of {len(sel)} (avgR of skipped {np.mean([r['R'] for r in out_]) if out_ else 0:+.4f}); "
                                    f"Sharpe {sa:.2f} -> {sb:.2f}")
        return out

    def combo_eval(sel, members, q75, label):
        """Apply a set of candidates together; Sharpe difference versus base."""
        def make(s_):
            rows = s_
            if "stop_rule" in members: rows = [r for r in rows if r["risk_atr"] <= STOP_MAX_ATR]
            if "session" in members: rows = [r for r in rows if SESSION[0] <= r["hour"] <= SESSION[1]]
            if "cluster_cap" in members: rows = [r for r, k in zip(rows, cluster_capped(rows)) if k]
            ms = defaultdict(float)
            for r in rows:
                v = r["R_retest"] if "retest" in members else (r["R_chand"] if "chandelier" in members else r["R"])
                if v is None: continue
                w_ = SIZE_TOP if ("sizing" in members and r["score"] >= q75) else 1.0
                if "pyramid" in members and r["R_add"] is not None and "retest" not in members:
                    v = (v + r["R_add"]) / 2
                ms[iso(r["entry_ts"])[:7]] += v * w_
            return ms
        d, t, sa, sb = sharpe_diff_t(sel, lambda s_: monthly(s_), make)
        return d, t, f"{'+'.join(members) or 'nothing'}: Sharpe {sa:.2f} -> {sb:.2f}"

    expl = [r for r in trades if r["year"] < SPLIT_YEAR]; hold = [r for r in trades if r["year"] >= SPLIT_YEAR]
    q75 = float(np.quantile([r["score"] for r in expl], 0.75))
    ex = evaluate(expl, "exploration", q75)
    positives = [c for c in CANDIDATES if ex[c][0] > 0]           # fixed BEFORE the holdout is examined
    L = [f"# v3 candidates on top of v2: explored 2008 to 2016, tested once on 2017 to 2026\n",
         f"Base = v2 (cost cap + tier cut). {len(expl)} exploration trades, {len(hold)} holdout trades. "
         f"{N_TESTS} preregistered holdout tests, one sided z **{Z:.2f}**. Costs 2 ticks per round trip. "
         f"Sizing quartile threshold and combo_B membership were fixed on the exploration half.\n",
         f"combo_A = stop_rule + chandelier. combo_B = exploration positives = {' + '.join(positives) or 'none'}.\n",
         "## Exploration half (for choosing, not for deciding)\n", "| candidate | effect | t | detail |", "|---|---|---|---|"]
    for k, (e, t, d) in ex.items(): L.append(f"| {k} | {e:+.4f} | {t:.2f} | {d} |")
    ho = evaluate(hold, "holdout", q75)
    ho["combo_A"] = combo_eval(hold, ["stop_rule", "chandelier"], q75, "A")
    ho["combo_B"] = combo_eval(hold, positives, q75, "B")
    L += ["\n## Holdout 2017 to 2026 (the preregistered tests)\n", "| test | effect | t | verdict | detail |", "|---|---|---|---|---|"]
    for k, (e, t, d) in ho.items():
        verdict = "reference" if k == "base" else ("PASS" if t > Z else "no")
        L.append(f"| {k} | {e:+.4f} | {t:.2f} | {verdict} | {d} |")
    L.append("\nEffect units: avgR difference for stop_rule, session, chandelier; Sharpe difference for retest, pyramid, "
             "sizing, cluster_cap and the combos. The stop rule, session and chandelier are on their third look at this "
             "holdout; weigh a PASS there accordingly.")
    open(os.path.join(OUT, "v3_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/v3_report.md, {OUT}/v3_trades.csv")


if __name__ == "__main__":
    main()
