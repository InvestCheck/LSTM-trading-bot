#!/usr/bin/env python3
"""Where to rest the order: the deeper of the two lines, or the refit line?

The engine's entry price is the refit line, but a break needs BOTH the raw hull
line and the refit line breached. The live bot rests at the deeper of the two
(guaranteed confirmation, worse fill on 26% of trades, about 0.035R). Resting
at the refit line gives the engine's price but adds scratches when the raw line
is not reached by the close.

This simulates both placements bar by bar over the full history, exactly as the
live bot places orders: only while the engine is flat, v2 gate at placement
(cost cap + frozen tier score), one order per direction at the level touched
first, fill at the level (or the open if gapped), confirmed when the engine
signals on that bar, otherwise scratched at that bar's close. Costs 2 ticks.

Preregistered comparison (one test): per touch P&L in ATR, refit placement
minus deeper placement, quarter block bootstrap, one sided z 1.64, on
2017 to 2026. 2008 to 2016 reported for reference.

Usage (repo folder):  python3 research_placement.py DATA_DIR [--symbols ...]
Writes research/placement_report.md.
"""
import os, sys, csv, math, json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from statistics import NormalDist
import numpy as np

from backtest_hull import load_series, ema, atr, pivots
from entry_scan import _refit, _stop_for, MINSPAN, MAXSPAN, TOL, BRK_TOL, K
from research_exits import harvest, exit_engine, quarter
from tier import NAMES, CLASSES
from batch_backtest import build_catalog, iso
from instruments import TICKS
from research_model import TICK_FIX
from ib_contracts import UNIVERSE

OUT = "research"
WARMUP_DAYS = 60
SPLIT_YEAR = 2017
BOOT_REPS, SEED = 400, 41
Z = NormalDist().inv_cdf(0.95)


class Gate:
    def __init__(self):
        m = json.load(open("research/tier_model.json")); cfg = json.load(open("v2_config.json"))
        assert m["names"] == NAMES
        self.mu, self.sd = np.array(m["mu"]), np.array(m["sd"]); self.lo, self.hi = np.array(m["clip_lo"]), np.array(m["clip_hi"])
        self.w, self.b, self.cutoff, self.zc = np.array(m["weights"]), m["intercept"], m["cutoff"], m.get("z_clip", 5.0)
        self.cheap, self.inst_cost = set(cfg["cheap"]), cfg["inst_cost"]

    def score(self, sym, D, p, d, entry, stop, stop_src, touches, span, next_ts):
        C, H, L, A, e21, e50, e200 = D["C"], D["H"], D["L"], D["A"], D["e21"], D["e50"], D["e200"]
        ap = A[p] if A[p] > 0 else 1e-12
        bandp = e21[p] + 3.5 * ap if d > 0 else e21[p] - 3.5 * ap
        hi1, lo1 = D["hi1"][p], D["lo1"][p]
        dt = datetime.fromtimestamp(int(next_ts), timezone.utc)
        cls = next((c for c, lst in CLASSES.items() if sym in lst), "OTHER")
        x = [d * (C[p] - e21[p]) / ap, d * (C[p] - e50[p]) / ap, d * (C[p] - e200[p]) / ap, d * (bandp - entry) / ap,
             d * (C[p] - C[max(0, p - 5)]) / ap, d * (C[p] - C[max(0, p - 20)]) / ap,
             ((entry - hi1) if d > 0 else (lo1 - entry)) / ap,
             ap / max(1e-12, float(np.mean(A[max(0, p - 500):p]))) if p > 50 else 1.0,
             abs(entry - stop) / ap, math.log(max(1, span)), touches, 1.0 if d > 0 else 0.0,
             1.0 if stop_src == "ema" else 0.0, math.sin(2 * math.pi * dt.hour / 24), math.cos(2 * math.pi * dt.hour / 24),
             1.0 if dt.weekday() == 6 else 0.0, self.inst_cost.get(sym, 0.1)] + [1.0 if cls == c else 0.0 for c in CLASSES]
        x = np.array(x, float); x[~np.isfinite(x)] = 0.0
        z = np.clip((np.clip(x, self.lo, self.hi) - self.mu) / self.sd, -self.zc, self.zc)
        return float(self.b + z @ self.w)


REFRESH = 1          # refit refreshed every bar while price is within 1 ATR of the line (touch counts change bar by bar)


def at_least_one_new_pivot(piv, since, upto, arr, a, m, d):
    for q in piv[since:upto]:
        ln = arr[a] + m * (q - a); g = (arr[q] - ln) if d < 0 else (ln - arr[q])
        if -BRK_TOL * arr[q] <= g <= 0.005 * arr[q]: return True
    return False


def rolling_extreme(x, w, fn_max=True):
    from collections import deque
    out = np.empty(len(x)); dq = deque()
    for i, v in enumerate(x):
        while dq and (x[dq[-1]] <= v if fn_max else x[dq[-1]] >= v): dq.pop()
        dq.append(i)
        if dq[0] <= i - w: dq.popleft()
        out[i] = x[dq[0]]
    return out


def simulate(sym, path, start_ts, gate, tick):
    T, O, H, L, C = load_series(path); n = len(C)
    e21, e50, e200, A = ema(C, 21), ema(C, 50), ema(C, 200), atr(H, L, C, 14)
    D = dict(T=T, O=O, H=H, L=L, C=C, e21=e21, e50=e50, e200=e200, A=A,
             hi1=rolling_extreme(H, 5800, True), lo1=rolling_extreme(L, 5800, False))
    PH, PL = pivots(H, L, K)
    # engine's own trades (one position rule) for flat/confirm, via the research harvest replay
    _, sigs = harvest(path, start_ts=start_ts)
    by_bar = defaultdict(list)
    for sg in sigs: by_bar[sg["t0"]].append(sg)
    engine, busy, taken, taken_at = {}, -1, set(), {}
    for t in sorted(by_bar):
        if t < busy: continue
        for sg in sorted(by_bar[t], key=lambda x: x["order"]):
            if sg["edge"] in taken: continue
            taken.add(sg["edge"]); taken_at[sg["edge"]] = t; ei, ex, _, _ = exit_engine(D, sg); busy = ei
            engine[t] = (sg, ei, ex); break
    in_pos = np.zeros(n, bool)
    for t, (sg, ei, ex) in engine.items(): in_pos[t:ei] = True   # engine holds from t up to (not incl.) exit bar
    start = int(np.searchsorted(T, start_ts))

    sh, rh, ih, il = [], [], 0, 0
    cache, dead, seen = {}, set(), set()   # edge -> (p1, s, tt, il_or_ih at compute); pierced raw lines
    pending = {"deep": {}, "refit": {}}   # dir -> order placed for this bar
    results = {"deep": [], "refit": []}
    def sl_low(i, j): return (L[j] - L[i]) / (j - i)
    def sl_high(i, j): return (H[j] - H[i]) / (j - i)

    for t in range(210, n):
        # ---- settle orders placed at t-1 for bar t
        for mode in ("deep", "refit"):
            for d, o in pending[mode].items():
                trig = o["trigger"]
                touched = (L[t] <= trig) if d < 0 else (H[t] >= trig)
                if not touched: continue
                fill = (O[t] if O[t] < trig else trig) if d < 0 else (O[t] if O[t] > trig else trig)
                a = A[t] if A[t] > 0 else 1e-12
                if t in engine and engine[t][0]["dir"] == d:
                    sg, ei, ex = engine[t]
                    s2 = dict(sg, entry=fill); ei2, ex2, _, _ = exit_engine(D, s2)
                    Rf = abs(fill - sg["stop0"])
                    r = ((ex2 - fill) / Rf * d - (2.0 * tick / Rf if tick else 0.0)) if Rf > 0 else 0.0
                    results[mode].append(dict(t=t, ts=int(T[t]), kind="confirmed", atr=(ex2 - fill) * d / a - (2 * tick / a if tick else 0), R=r,
                                              fill_vs_engine=(fill - sg["entry"]) * d / abs(sg["entry"] - sg["stop0"])))
                else:
                    results[mode].append(dict(t=t, ts=int(T[t]), kind="scratch", atr=(C[t] - fill) * d / a - (2 * tick / a if tick else 0), R=None,
                                              fill_vs_engine=None))
            pending[mode] = {}
        # ---- hull update (engine order of operations)
        while il < len(PL) and PL[il] + K <= t:
            p = PL[il]
            while len(sh) >= 2 and sl_low(sh[-2], sh[-1]) >= sl_low(sh[-1], p): sh.pop()
            sh.append(p); il += 1
        while ih < len(PH) and PH[ih] + K <= t:
            p = PH[ih]
            while len(rh) >= 2 and sl_high(rh[-2], rh[-1]) <= sl_high(rh[-1], p): rh.pop()
            rh.append(p); ih += 1
        if t < start or t + 1 >= n or in_pos[t]: continue
        # ---- place orders for bar t+1 from data through t (the live bot at the close of t)
        nxt = t + 1
        for d, hull, piv, arr, npiv in ((-1, sh, PL, L, il), (1, rh, PH, H, ih)):
            best = {"deep": None, "refit": None}
            for i in range(1, len(hull)):
                a, b = hull[i - 1], hull[i]; key = (int(a), int(b), 's' if d < 0 else 'r')
                if key in dead or (key in taken_at and taken_at[key] <= t): continue
                m = (arr[b] - arr[a]) / (b - a)
                if (d < 0 and m <= 0) or (d > 0 and m >= 0): continue
                if (nxt - a) < MINSPAN or (nxt - a) > MAXSPAN: continue
                if key not in seen:                      # the engine's full no pierce check, once per edge
                    seen.add(key); zz = np.arange(a, t + 1); ln = arr[a] + m * (zz - a)
                    if (d < 0 and np.any(L[a:t + 1] < ln - TOL * L[a:t + 1])) or \
                       (d > 0 and np.any(H[a:t + 1] > ln + TOL * H[a:t + 1])):
                        dead.add(key); continue
                lp = arr[a] + m * (t - a)
                if (d < 0 and L[t] < lp - TOL * L[t]) or (d > 0 and H[t] > lp + TOL * H[t]):
                    dead.add(key); continue
                if (d < 0 and not L[t] > lp) or (d > 0 and not H[t] < lp): continue
                lt = arr[a] + m * (nxt - a)
                # refit, cached; recompute when a new pivot near the line confirmed or the cached line is pierced
                # refit cache. Touch counts and the best pair drift with every bar, so the cached refit is
                # refreshed whenever price is within 1 ATR of the raw line and the cache is older than
                # REFRESH bars, on any new pivot near the line, and when the cached line is pierced.
                c = cache.get(key)
                near = abs((L[t] if d < 0 else H[t]) - lp) <= 1.0 * A[t]
                recompute = c is None or (near and t - c[4] >= REFRESH)
                if c is not None and c[0] is not None and not recompute:
                    p1, s, tt, at_npiv, _ = c
                    lz = arr[p1] + s * (t - p1)
                    if (d < 0 and L[t] < lz - BRK_TOL * L[t]) or (d > 0 and H[t] > lz + BRK_TOL * H[t]): recompute = True
                    elif at_npiv != npiv:
                        for q in piv[at_npiv:npiv]:
                            ln = arr[a] + m * (q - a); g = (arr[q] - ln) if d < 0 else (ln - arr[q])
                            if -BRK_TOL * arr[q] <= g <= 0.005 * arr[q]: recompute = True; break
                        if not recompute: cache[key] = (p1, s, tt, npiv, c[4])
                elif c is not None and c[0] is None and not recompute and at_least_one_new_pivot(piv, c[3], npiv, arr, a, m, d):
                    recompute = True
                if recompute:
                    rf = _refit(T, H, L, piv[:npiv], arr, 1 if d < 0 else -1, a, m, nxt, set(hull), check_break=False)
                    if rf is None: cache[key] = (None, None, None, npiv, t); continue
                    p1, s, _, tt = rf; cache[key] = (p1, s, tt, npiv, t)
                p1, s, tt, _, _ = cache[key]
                if p1 is None: continue
                lt2 = arr[p1] + s * (nxt - p1); lp2 = arr[p1] + s * (t - p1)
                if (d < 0 and not L[t] > lp2) or (d > 0 and not H[t] < lp2): continue
                stop, src = _stop_for(H, L, e200, A, sh, rh, d, lt2, t)
                if stop is None or (d < 0 and stop - lt2 <= 0) or (d > 0 and lt2 - stop <= 0): continue
                if sym not in gate.cheap: continue
                sc = gate.score(sym, D, t, d, lt2, stop, src, len(tt), nxt - a, int(T[t]) + 3600)
                if sc < gate.cutoff: continue
                cand = dict(dir=d, stop=stop, refit=float(lt2), raw=float(lt))
                for mode, trig in (("deep", min(lt, lt2) if d < 0 else max(lt, lt2)), ("refit", lt2)):
                    if best[mode] is None or (d < 0 and trig > best[mode]["trigger"]) or (d > 0 and trig < best[mode]["trigger"]):
                        best[mode] = dict(cand, trigger=float(trig))
            for mode in ("deep", "refit"):
                if best[mode] is not None: pending[mode][d] = best[mode]
    return results, [int(T[t]) for t in engine if t >= start]


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_placement.py DATA_DIR [--symbols ...]")
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(args[0]); gate = Gate()
    allres = {"deep": [], "refit": []}; engine_ts = []
    for sym in syms:
        if sym not in cat or sym not in gate.cheap: continue
        tick = TICK_FIX.get(sym, TICKS.get(sym, 0.0))
        T = load_series(cat[sym])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        res, eng = simulate(sym, cat[sym], start_ts, gate, tick); engine_ts += eng
        for mode in res:
            for r in res[mode]: r["symbol"] = sym; allres[mode].append(r)
        print(f"{sym:5s} engine trades {len(eng):4d} | deep: {len(res['deep'])} touches, "
              f"{sum(1 for r in res['deep'] if r['kind']=='confirmed')} confirmed | refit: {len(res['refit'])} touches, "
              f"{sum(1 for r in res['refit'] if r['kind']=='confirmed')} confirmed")

    def summarize(rows):
        yrs = max(1e-9, (max(r["ts"] for r in rows) - min(r["ts"] for r in rows)) / (365.25 * 86400)) if rows else 1
        conf = [r for r in rows if r["kind"] == "confirmed"]; scr = [r for r in rows if r["kind"] == "scratch"]
        return dict(touches=len(rows), confirmed=len(conf), scratched=len(scr), yrs=yrs,
                    conf_R=np.mean([r["R"] for r in conf]) if conf else 0, scr_atr=np.mean([r["atr"] for r in scr]) if scr else 0,
                    per_touch=np.mean([r["atr"] for r in rows]) if rows else 0, total_atr=sum(r["atr"] for r in rows),
                    fill_vs_engine=np.mean([r["fill_vs_engine"] for r in conf]) if conf else 0)

    def diff_t(a, b):
        """per touch ATR, b minus a, quarter block bootstrap over each mode's own touches."""
        qa, qb = defaultdict(list), defaultdict(list)
        for r in a: qa[quarter(r["ts"])].append(r["atr"])
        for r in b: qb[quarter(r["ts"])].append(r["atr"])
        keys = sorted(set(qa) | set(qb)); rng = np.random.default_rng(SEED); diffs = []
        for _ in range(BOOT_REPS):
            pick = rng.integers(0, len(keys), len(keys))
            xa = [v for i in pick for v in qa.get(keys[i], [])]; xb = [v for i in pick for v in qb.get(keys[i], [])]
            if xa and xb: diffs.append(np.mean(xb) - np.mean(xa))
        d = (np.mean([r["atr"] for r in b]) if b else 0) - (np.mean([r["atr"] for r in a]) if a else 0)
        sd = float(np.std(diffs)) if diffs else float("nan")
        return d, (d / sd if sd and sd > 0 else float("nan"))

    L = ["# Resting order placement: deeper line vs refit line (v2 gate, engine flat only)\n",
         "Both placements simulated bar by bar as the live bot would place them. Confirmed = the engine signalled on the "
         "fill bar (scored with the actual fill and the engine's exit); scratched = closed at that bar's close. Costs 2 ticks. "
         "One preregistered test: per touch P&L in ATR, refit minus deeper, 2017 to 2026, one sided z 1.64.\n",
         "| period | placement | touches | confirmed (of engine trades) | scratched | confirmed avgR | fill vs engine (R) | scratch avg (ATR) | per touch (ATR) | ATR/yr |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    verdict_line = ""
    for period, cond in (("2008-2016", lambda r: r["ts"] < datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp()),
                         ("2017-2026", lambda r: r["ts"] >= datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp())):
        sub = {m: [r for r in allres[m] if cond(r)] for m in allres}
        n_eng = sum(1 for ts in engine_ts if cond(dict(ts=ts)))
        for m in ("deep", "refit"):
            s_ = summarize(sub[m])
            L.append(f"| {period} | {m} | {s_['touches']} | {s_['confirmed']} of {n_eng} engine | {s_['scratched']} | {s_['conf_R']:+.4f} | "
                     f"{s_['fill_vs_engine']:+.4f} | {s_['scr_atr']:+.4f} | {s_['per_touch']:+.4f} | {s_['total_atr'] / s_['yrs']:+.1f} |")
        d, t = diff_t(sub["deep"], sub["refit"])
        tag = "PASS" if (period == "2017-2026" and t > Z) else ("no" if period == "2017-2026" else "reference")
        L.append(f"| {period} | refit minus deeper | | | | | | | {d:+.4f} (t {t:.2f}) | {tag} |")
    L.append("\nfill vs engine: positive means the fill was worse than the engine's assumed entry, in R. "
             "Deeper placement should show ~+0.03; refit placement should show ~0 with more scratches.")
    open(os.path.join(OUT, "placement_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/placement_report.md")


if __name__ == "__main__":
    main()
