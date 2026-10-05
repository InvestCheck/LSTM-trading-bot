#!/usr/bin/env python3
"""Research harness: exits, filters and the band fade on the engine's own entries.

Separate from the forward test. Nothing here touches the frozen configuration,
the live bot, or the protocol. The test list below is fixed BEFORE running, and
the number of tests sets the significance threshold (Bonferroni, one sided).

What it does
  1. HARVEST every signal the frozen entry logic fires (MINSPAN 2160, MAXSPAN
     17520, intrabar, causal) for each instrument, ignoring whether the engine
     was flat at the time. This is the engine's entry code with the position
     manager removed, so every exit variant is evaluated on the same entries.
     Self check: applying the engine's own exit to the harvest, one position
     per instrument, must reproduce the engine's trade list.
  2. FEATURES at the entry bar, nothing after it: distance from the 21/50/200
     EMA in ATRs (signed by direction), room to the 3.5 ATR parabolic band,
     move over the last 5 and 20 bars in ATRs (signed), distance from the 1y
     and 5y extreme in ATRs, ATR relative to its 500 bar mean, hour, weekday,
     touches, span, initial risk in ATRs.
  3. EXIT VARIANTS on the harvest (one position per instrument):
     engine, engine without the parabolic, fixed 2R target, half off at 1R
     then engine, 3 ATR chandelier trail, 48 bar time stop.
  4. FILTERS on the engine's trades: in vs out, listed in FILTERS below.
  5. BAND FADE: signals that fire with less than X ATR of room to the band are
     traded the OTHER way, stop 0.5 ATR beyond the band and trailing with it,
     target the 21 EMA, 96 bar time stop. X in {0.5, 0.0}.

Costs: 2 ticks per round trip (instruments.py tick, vendor price units).
Statistic: pooled avgR with a block bootstrap over calendar quarters.

Usage (repo folder):
  python3 research_exits.py DATA_DIR [--symbols GC ES ...]
Writes research/signals.csv (one row per signal, every variant's R) and
research/report.md.
"""
import os, sys, csv, math, statistics as st
from collections import deque, defaultdict
from datetime import datetime, timezone
from statistics import NormalDist
import numpy as np

from backtest_hull import load_series, ema, atr, pivots, run
from batch_backtest import build_catalog, iso
from instruments import TICKS
from ib_contracts import UNIVERSE

MINSPAN, MAXSPAN, WARMUP_DAYS = 2160, 17520, 60
OUT = "research"
BOOT_REPS, SEED = 400, 7

EXITS = ["engine", "engine_noparab", "target_2R", "half_at_1R", "chandelier_3atr", "time_48"]
FILTERS = {                                  # name: (feature, op, value)
    "room_ge_0.5":      ("room", ">=", 0.5),
    "room_ge_1.0":      ("room", ">=", 1.0),
    "above_e21":        ("d_e21", ">=", 0.0),
    "above_e200":       ("d_e200", ">=", 0.0),
    "no_fade_20bar":    ("mom20", ">=", -1.0),
    "near_1y_extreme":  ("ext_1y", ">=", -3.0),
    "calm_atr":         ("atr_ratio", "<=", 1.5),
    "ny_session":       ("hour", "in", (8, 16)),
}
FADE_THRESHOLDS = [0.5, 0.0]
N_TESTS = (len(EXITS) - 1) + len(FILTERS) + len(FADE_THRESHOLDS)
Z_CRIT = NormalDist().inv_cdf(1 - 0.05 / N_TESTS)


# ----------------------------------------------------------------------------
# 1. Harvest: run()'s entry detection with the position manager removed
# ----------------------------------------------------------------------------
def harvest(path, tol=0.0015, toltouch=0.0010, touch_band=0.0005, brk_tol=0.0002,
            SPANDAYS=7, K=3, MINTOUCH=3, TGAP=6, start_ts=None, fill="intrabar"):
    nextbar = (fill == "next")
    T, O, H, L, C = load_series(path); n = len(C)
    e21 = ema(C, 21); e200 = ema(C, 200); A = atr(H, L, C, 14)
    PH, PL = pivots(H, L, K)
    start = int(np.searchsorted(T, start_ts)) if start_ts else 0
    sh = []; rh = []; ih = 0; il = 0
    sigs = []; touches = []

    def sl_low(i, j): return (L[j] - L[i]) / (j - i)
    def sl_high(i, j): return (H[j] - H[i]) / (j - i)
    def sepidx(idxs):
        out = []
        for z in sorted(idxs):
            if not out or z - out[-1] >= TGAP: out.append(int(z))
        return out

    def refit(piv, arr, sign, a, m, t, hv, check_break=True):
        cand = []
        for p in piv:
            if p < a or p > t: continue
            if p > t - K: continue
            ln = arr[a] + m * (p - a); g = (arr[p] - ln) if sign > 0 else (ln - arr[p])
            if -brk_tol * arr[p] <= g <= 0.005 * arr[p]: cand.append(int(p))
        if len(cand) < MINTOUCH: return None
        best = None
        for x in range(len(cand)):
            p1 = cand[x]
            if p1 not in hv: continue
            if (T[t] - T[p1]) < SPANDAYS * 86400: continue
            for y in range(x + 1, len(cand)):
                p2 = cand[y]
                if p2 - p1 < TGAP: continue
                s = (arr[p2] - arr[p1]) / (p2 - p1)
                if (sign > 0 and s <= 0) or (sign < 0 and s >= 0): continue
                zz = np.arange(p1, t); lnz = arr[p1] + s * (zz - p1)
                if (sign > 0 and np.any(L[p1:t] < lnz - brk_tol * L[p1:t])) or \
                   (sign < 0 and np.any(H[p1:t] > lnz + brk_tol * H[p1:t])): continue
                lnt = arr[p1] + s * (t - p1); lnp = arr[p1] + s * (t - 1 - p1)
                if check_break:
                    if sign > 0:
                        if not (L[t] <= lnt and L[t - 1] > lnp): continue
                    else:
                        if not (H[t] >= lnt and H[t - 1] < lnp): continue
                g = (arr[p1:t] - lnz) if sign > 0 else (lnz - arr[p1:t])
                mask = (g >= -brk_tol * arr[p1:t]) & (g <= touch_band * arr[p1:t])
                tt = sepidx([int(z) for z in zz[mask]])
                if len(tt) >= MINTOUCH:
                    score = (len(tt), p2 - p1)
                    if best is None or score > best[0]: best = (score, int(p1), float(s), int(p2), tt)
        if best is None: return None
        _, p1, s, p2, tt = best
        return (p1, s, p2, tt)

    for t in range(210, n):
        while il < len(PL) and PL[il] + K <= t:
            p = PL[il]
            while len(sh) >= 2 and sl_low(sh[-2], sh[-1]) >= sl_low(sh[-1], p): sh.pop()
            sh.append(p); il += 1
        while ih < len(PH) and PH[ih] + K <= t:
            p = PH[ih]
            while len(rh) >= 2 and sl_high(rh[-2], rh[-1]) <= sl_high(rh[-1], p): rh.pop()
            rh.append(p); ih += 1
        if t < start: continue

        order = 0
        for i in range(1, len(sh)):
            a, b = sh[i - 1], sh[i]
            m = sl_low(a, b)
            if m <= 0 or (t - a) < MINSPAN or (t - a) > MAXSPAN: continue
            lt = L[a] + m * (t - a); lp = L[a] + m * (t - 1 - a)
            if not (L[t] <= lt and L[t - 1] > lp): continue
            zz = np.arange(a, t)
            if np.any(L[a:t] < L[a] + m * (zz - a) - tol * L[a:t]): continue
            # a resting sell stop at lt would have filled here (at the open if it gapped through)
            pre = refit(PL, L, 1, a, m, t, set(sh), check_break=False)
            preok = False
            if pre is not None:
                lvl = L[pre[0]] + pre[1] * (t - pre[0]); fl = 1.0 * A[t - 1]
                preok = any((H[rh[j - 1]] + (H[rh[j]] - H[rh[j - 1]]) / (rh[j] - rh[j - 1]) * (t - rh[j - 1])) > lvl + fl
                            and rh[j] >= t - 720 and rh[j - 1] >= t - 2880 for j in range(1, len(rh))) \
                        or e200[t - 1] > lvl + fl
            touches.append(dict(t=int(t), dir=-1, fill=float(O[t] if O[t] < lt else lt), order=order, pre=preok))
            rf = refit(PL, L, 1, a, m, t, set(sh))
            if rf is None: continue
            a2, m2, last2, tch = rf
            lt = L[a2] + m2 * (t - a2)
            if nextbar:
                if t + 1 >= n: continue
                entry = O[t + 1]
            else:
                entry = O[t] if O[t] < lt else lt
            floor = 1.0 * A[t]
            cands = []
            for j in range(1, len(rh)):
                aa, bb = rh[j - 1], rh[j]; mm = (H[bb] - H[aa]) / (bb - aa); val = H[aa] + mm * (t - aa)
                if val > entry + floor and bb >= t - 720 and aa >= t - 2880: cands.append(float(val))
            cands.sort()
            if cands: stop = cands[0]; stop_src = 'auto'
            elif e200[t] > entry + floor: stop = float(e200[t]); stop_src = 'ema'
            else: continue
            if stop - entry <= 0: continue
            sigs.append(dict(dir=-1, t0=int(t), entry=float(entry), stop0=float(stop), a=int(a2),
                             kind='sup', touches=len(tch), stop_src=stop_src, edge=(int(a), int(b), 's'),
                             order=order)); order += 1
        if True:
            for i in range(1, len(rh)):
                a, b = rh[i - 1], rh[i]
                m = sl_high(a, b)
                if m >= 0 or (t - a) < MINSPAN or (t - a) > MAXSPAN: continue
                lt = H[a] + m * (t - a); lp = H[a] + m * (t - 1 - a)
                if not (H[t] >= lt and H[t - 1] < lp): continue
                zz = np.arange(a, t)
                if np.any(H[a:t] > H[a] + m * (zz - a) + tol * H[a:t]): continue
                pre = refit(PH, H, -1, a, m, t, set(rh), check_break=False)
                preok = False
                if pre is not None:
                    lvl = H[pre[0]] + pre[1] * (t - pre[0]); fl = 1.0 * A[t - 1]
                    preok = any((L[sh[j - 1]] + (L[sh[j]] - L[sh[j - 1]]) / (sh[j] - sh[j - 1]) * (t - sh[j - 1])) < lvl - fl
                                and sh[j] >= t - 720 and sh[j - 1] >= t - 2880 for j in range(1, len(sh))) \
                            or e200[t - 1] < lvl - fl
                touches.append(dict(t=int(t), dir=1, fill=float(O[t] if O[t] > lt else lt), order=order, pre=preok))
                rf = refit(PH, H, -1, a, m, t, set(rh))
                if rf is None: continue
                a2, m2, last2, tch = rf
                lt = H[a2] + m2 * (t - a2)
                if nextbar:
                    if t + 1 >= n: continue
                    entry = O[t + 1]
                else:
                    entry = O[t] if O[t] > lt else lt
                floor = 1.0 * A[t]
                cands = []
                for j in range(1, len(sh)):
                    aa, bb = sh[j - 1], sh[j]; mm = (L[bb] - L[aa]) / (bb - aa); val = L[aa] + mm * (t - aa)
                    if val < entry - floor and bb >= t - 720 and aa >= t - 2880: cands.append(float(val))
                cands.sort(reverse=True)
                if cands: stop = cands[0]; stop_src = 'auto'
                elif e200[t] < entry - floor: stop = float(e200[t]); stop_src = 'ema'
                else: continue
                if entry - stop <= 0: continue
                sigs.append(dict(dir=1, t0=int(t), entry=float(entry), stop0=float(stop), a=int(a2),
                                 kind='res', touches=len(tch), stop_src=stop_src, edge=(int(a), int(b), 'r'),
                                 order=order)); order += 1
    return dict(T=T, O=O, H=H, L=L, C=C, e21=e21, e50=ema(C, 50), e200=e200, A=A, touches=touches), sigs


# ----------------------------------------------------------------------------
# 2. Features at the entry bar
# ----------------------------------------------------------------------------
def rolling_extreme(x, w, fn_max=True):
    """out[i] = max (or min) of x[i-w+1 .. i], O(n) with a monotonic deque."""
    out = np.empty(len(x)); dq = deque()
    for i, v in enumerate(x):
        while dq and (x[dq[-1]] <= v if fn_max else x[dq[-1]] >= v): dq.pop()
        dq.append(i)
        if dq[0] <= i - w: dq.popleft()
        out[i] = x[dq[0]]
    return out


def features(D, s):
    t, d, entry = s["t0"], s["dir"], s["entry"]
    C, H, L, A, e21, e50, e200 = D["C"], D["H"], D["L"], D["A"], D["e21"], D["e50"], D["e200"]
    a = A[t] if A[t] > 0 else 1e-12
    band = e21[t] + 3.5 * a if d > 0 else e21[t] - 3.5 * a
    f = dict(
        d_e21=d * (C[t] - e21[t]) / a, d_e50=d * (C[t] - e50[t]) / a, d_e200=d * (C[t] - e200[t]) / a,
        room=d * (band - entry) / a,
        mom5=d * (C[t] - C[max(0, t - 5)]) / a, mom20=d * (C[t] - C[max(0, t - 20)]) / a,
        ext_1y=((entry - D["hi1"][t]) if d > 0 else (D["lo1"][t] - entry)) / a,
        ext_5y=((entry - D["hi5"][t]) if d > 0 else (D["lo5"][t] - entry)) / a,
        atr_ratio=a / max(1e-12, float(np.mean(A[max(0, t - 500):t]))) if t > 50 else 1.0,
        hour=datetime.fromtimestamp(int(D["T"][t]), timezone.utc).hour,
        dow=datetime.fromtimestamp(int(D["T"][t]), timezone.utc).weekday(),
        risk_atr=abs(entry - s["stop0"]) / a,
    )
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}


# ----------------------------------------------------------------------------
# 3. Exit variants: each returns (exit_idx, exit_px, why, mfe_R)
# ----------------------------------------------------------------------------
def exit_engine(D, s, parabolic=True):
    O, H, L, C, e21, e200, A = D["O"], D["H"], D["L"], D["C"], D["e21"], D["e200"], D["A"]
    t0, d, entry, stp = s["t0"], s["dir"], s["entry"], s["stop0"]
    R = abs(entry - stp); phase = 1; stt = stp; mfe = 0.0; n = len(C)
    for t in range(t0 + 1, n):
        ex = None; why = ''
        if d > 0:
            mfe = max(mfe, (H[t] - entry) / R)
            if parabolic and H[t] - e21[t] >= 3.5 * A[t]: ex = e21[t] + 3.5 * A[t]; why = 'parabolic'
            if ex is None and phase == 1:
                if L[t] <= stt: ex = stt; why = 'stop'
                elif H[t] >= entry + R: phase = 2; stt = entry
            if ex is None and phase == 2:
                if L[t] <= entry: ex = entry; why = 'BE'
                elif C[t] < e21[t]: ex = C[t]; why = '21EMA'
        else:
            mfe = max(mfe, (entry - L[t]) / R)
            if parabolic and e21[t] - L[t] >= 3.5 * A[t]: ex = e21[t] - 3.5 * A[t]; why = 'parabolic'
            if ex is None and phase == 1:
                if H[t] >= stt: ex = stt; why = 'stop'
                elif L[t] <= entry - R: phase = 2; stt = entry
            if ex is None and phase == 2:
                if H[t] >= entry: ex = entry; why = 'BE'
                elif C[t] > e21[t]: ex = C[t]; why = '21EMA'
        if ex is not None:
            return t, float(ex), why, mfe
        if phase == 1:
            if d > 0 and e200[t] < C[t] and e200[t] > stt and abs(e200[t] - entry) >= 0.5 * R: stt = e200[t]
            if d < 0 and e200[t] > C[t] and e200[t] < stt and abs(e200[t] - entry) >= 0.5 * R: stt = e200[t]
    return n - 1, float(C[-1]), 'eod', mfe


def exit_target(D, s, k=2.0):
    H, L, C = D["H"], D["L"], D["C"]
    t0, d, entry, stp = s["t0"], s["dir"], s["entry"], s["stop0"]
    R = abs(entry - stp); tgt = entry + d * k * R; mfe = 0.0
    for t in range(t0 + 1, len(C)):
        mfe = max(mfe, d * ((H[t] if d > 0 else L[t]) - entry) / R)
        if (d > 0 and L[t] <= stp) or (d < 0 and H[t] >= stp): return t, stp, 'stop', mfe
        if (d > 0 and H[t] >= tgt) or (d < 0 and L[t] <= tgt): return t, tgt, 'target', mfe
    return len(C) - 1, float(C[-1]), 'eod', mfe


def exit_chandelier(D, s, k=3.0):
    H, L, C, A = D["H"], D["L"], D["C"], D["A"]
    t0, d, entry, stp = s["t0"], s["dir"], s["entry"], s["stop0"]
    R = abs(entry - stp); stt = stp; best = entry; mfe = 0.0
    for t in range(t0 + 1, len(C)):
        mfe = max(mfe, d * ((H[t] if d > 0 else L[t]) - entry) / R)
        if (d > 0 and L[t] <= stt) or (d < 0 and H[t] >= stt): return t, stt, 'trail', mfe
        best = max(best, C[t]) if d > 0 else min(best, C[t])
        stt = max(stt, best - k * A[t]) if d > 0 else min(stt, best + k * A[t])
    return len(C) - 1, float(C[-1]), 'eod', mfe


def exit_time(D, s, nbars=48):
    H, L, C = D["H"], D["L"], D["C"]
    t0, d, entry, stp = s["t0"], s["dir"], s["entry"], s["stop0"]
    R = abs(entry - stp); mfe = 0.0
    for t in range(t0 + 1, min(len(C), t0 + nbars + 1)):
        mfe = max(mfe, d * ((H[t] if d > 0 else L[t]) - entry) / R)
        if (d > 0 and L[t] <= stp) or (d < 0 and H[t] >= stp): return t, stp, 'stop', mfe
        if t == t0 + nbars: return t, float(C[t]), 'time', mfe
    return len(C) - 1, float(C[-1]), 'eod', mfe


def exit_fade(D, s):
    """Trade AGAINST the break, entered at the next bar's open (after seeing the
    close that showed no room). Stop 0.5 ATR beyond BOTH the entry bar's extreme
    and the parabolic band, trailing with the band but never below breakeven;
    target the 21 EMA; 96 bar time stop. Returns (exit_idx, R, why) or None."""
    O, H, L, C, e21, A = D["O"], D["H"], D["L"], D["C"], D["e21"], D["A"]
    t0, d0 = s["t0"], s["dir"]
    if t0 + 1 >= len(C): return None
    d = -d0; a = A[t0]; entry = O[t0 + 1]
    if d0 > 0:
        band0 = e21[t0] + 3.5 * a; stt = max(H[t0], band0) + 0.5 * a
    else:
        band0 = e21[t0] - 3.5 * a; stt = min(L[t0], band0) - 0.5 * a
    R = abs(stt - entry)
    if R < 0.1 * a: return None
    for t in range(t0 + 1, min(len(C), t0 + 97)):
        if d < 0:
            if H[t] >= stt: return t, (stt - entry) / R * d, 'stop', R
            if L[t] <= e21[t]: return t, (e21[t] - entry) / R * d, 'target', R
            stt = max(min(stt, e21[t] + 4.0 * A[t]), entry)
        else:
            if L[t] <= stt: return t, (stt - entry) / R * d, 'stop', R
            if H[t] >= e21[t]: return t, (e21[t] - entry) / R * d, 'target', R
            stt = min(max(stt, e21[t] - 4.0 * A[t]), entry)
        if t == t0 + 96: return t, (C[t] - entry) / R * d, 'time', R
    return len(C) - 1, (C[-1] - entry) / R * d, 'eod', R


def run_variant(name, D, s):
    if name == "engine": return exit_engine(D, s)
    if name == "engine_noparab": return exit_engine(D, s, parabolic=False)
    if name == "target_2R": return exit_target(D, s, 2.0)
    if name == "chandelier_3atr": return exit_chandelier(D, s, 3.0)
    if name == "time_48": return exit_time(D, s, 48)
    if name == "half_at_1R":
        ei, ex, why, mfe = exit_engine(D, s)
        return ei, ex, ("half+" + why) if mfe >= 1.0 else why, mfe
    raise ValueError(name)


def r_of(s, ex, variant_why=None, mfe=0.0, name=""):
    R = abs(s["entry"] - s["stop0"])
    r = (ex - s["entry"]) / R * s["dir"]
    if name == "half_at_1R" and mfe >= 1.0:
        r = 0.5 * 1.0 + 0.5 * r
    return r


# ----------------------------------------------------------------------------
# 4. Stats
# ----------------------------------------------------------------------------
def quarter(ts):
    dt = datetime.fromtimestamp(int(ts), timezone.utc)
    return dt.year * 4 + (dt.month - 1) // 3


def block_t(values, quarters, reps=BOOT_REPS, seed=SEED):
    """Mean / bootstrap std of the mean, resampling calendar quarters."""
    values = np.asarray(values, float)
    if len(values) < 10: return float("nan"), float("nan")
    by_q = defaultdict(list)
    for v, q in zip(values, quarters): by_q[q].append(v)
    keys = list(by_q); arrs = [np.asarray(by_q[k]) for k in keys]
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(reps):
        pick = rng.integers(0, len(arrs), len(arrs))
        cat = np.concatenate([arrs[i] for i in pick])
        means.append(cat.mean())
    sd = float(np.std(means))
    return float(values.mean()), (float(values.mean()) / sd if sd > 0 else float("nan"))


def summarize(rs):
    rs = np.asarray(rs, float)
    if not len(rs): return dict(n=0, avgR=0, win=0, PF=0, totalR=0)
    w = rs[rs > 0.01]; l = rs[rs < -0.01]
    return dict(n=len(rs), avgR=rs.mean(), win=(rs > 0.01).mean() * 100,
                PF=(w.sum() / abs(l.sum())) if len(l) and l.sum() else float("inf"), totalR=rs.sum())


# ----------------------------------------------------------------------------
# 5. Main
# ----------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_exits.py DATA_DIR [--symbols ...]")
    data_dir = args[0]
    fill = args[args.index("--fill") + 1] if "--fill" in args else "intrabar"
    if fill not in ("intrabar", "next"): sys.exit("--fill must be intrabar or next")
    global OUT
    OUT = os.path.join("research", fill)
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(data_dir)
    os.makedirs(OUT, exist_ok=True)
    print(f"fill mode: {fill}  (intrabar = the protocol's scored engine; next = entry at the next bar's "
          f"open, which is what the live bot actually does)")
    print(f"preregistered: {len(EXITS) - 1} exit comparisons, {len(FILTERS)} filters, "
          f"{len(FADE_THRESHOLDS)} fade thresholds = {N_TESTS} tests; one sided z threshold {Z_CRIT:.2f}\n")

    rows = []; engine_check = dict(engine_trades=0, reproduced=0); resting = {}
    for s in syms:
        if s not in cat: print(f"{s:5s} missing"); continue
        tick = TICKS.get(s, 0.0)
        T = load_series(cat[s])[0]
        start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(cat[s], start_ts=start_ts, fill=fill)
        D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
        D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
        # engine reference, for the self check (intrabar only: the engine's own fill='next' also
        # changes the trigger to the legacy break through rule, which is not the live bot's model)
        if fill == "intrabar":
            _, eng, _, _ = run(s, cat[s], 1.0, start_ts, CAP=1e12, MINSPAN=MINSPAN, MAXSPAN=MAXSPAN,
                               fill="intrabar", causal=True)
        else:
            eng = []
        eng_keys = {(x["t0"], x["dir"]): x for x in eng}
        # every variant: one position per instrument, same rule as the engine
        per_sig = {id(sg): dict(sg) for sg in sigs}
        for sg in sigs:
            for name in EXITS:
                per_sig[id(sg)][f"R_{name}"] = ""; per_sig[id(sg)][f"why_{name}"] = "skipped"
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        bars = sorted(by_bar)
        for name in EXITS:
            # exactly the engine's rule: when flat, take the first candidate on the bar whose
            # line has not been traded before; a line only counts as traded when it is taken
            busy, taken = -1, set()
            for t in bars:
                if t < busy: continue
                for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                    if sg["edge"] in taken: continue
                    taken.add(sg["edge"])
                    row = per_sig[id(sg)]
                    ei, ex, why, mfe = run_variant(name, D, sg)
                    r = r_of(sg, ex, why, mfe, name)
                    cost = (2.0 * tick) / abs(sg["entry"] - sg["stop0"]) if tick else 0.0
                    row[f"R_{name}"] = round(r - cost, 6); row[f"why_{name}"] = why
                    if name == "engine":
                        row["mfe"] = round(mfe, 4); row["exit_idx"] = ei; row["gross_engine"] = round(r, 6)
                    busy = ei
                    break
        # band fade: only on signals the engine took, costs charged, one fade at a time per instrument
        fade_busy = -1
        for sg in sorted(sigs, key=lambda x: (x["t0"], x["order"])):
            row = per_sig[id(sg)]
            row["R_fade"], row["why_fade"] = "", "skipped"
            if row["why_engine"] == "skipped" or sg["t0"] < fade_busy: continue
            fr = exit_fade(D, sg)
            if not fr:
                row["why_fade"] = "nostop"; continue
            ei, r, why, Rden = fr
            cost = (2.0 * tick) / Rden if tick else 0.0
            row["R_fade"] = round(r - cost, 6); row["why_fade"] = why
            fade_busy = ei
        if fill == "intrabar":
            # Resting order model: at each bar the bot is flat, one stop order per direction at the
            # first touchable line (OCO), filled at the line. Confirmed touches are the engine's
            # trades; unconfirmed ones are scratched at that bar's close. Everything in ATR units.
            taken_bars = {sg["t0"] for sg in sigs if per_sig[id(sg)]["why_engine"] != "skipped"}
            busy_until = {}
            for sg in sigs:
                r = per_sig[id(sg)]
                if r["why_engine"] != "skipped": busy_until[sg["t0"]] = r["exit_idx"]
            A, C = D["A"], D["C"]
            for model in ("naive", "prequalified"):
                flat_from = -1; conf_atr = []; scr_atr = []; n_touch = n_conf = 0; seen = set()
                for tc in sorted(D["touches"], key=lambda x: (x["t"], x["order"])):
                    t = tc["t"]
                    if model == "prequalified" and not tc["pre"]: continue
                    if t < flat_from or (t, tc["dir"]) in seen: continue
                    seen.add((t, tc["dir"])); n_touch += 1
                    if t in busy_until: flat_from = busy_until[t]
                    a = A[t] if A[t] > 0 else 1e-12
                    conf = next((x for x in by_bar.get(t, []) if x["dir"] == tc["dir"]
                                 and per_sig[id(x)]["why_engine"] != "skipped"), None)
                    if conf is not None:
                        n_conf += 1
                        conf_atr.append(per_sig[id(conf)]["R_engine"] * abs(conf["entry"] - conf["stop0"]) / a)
                    else:
                        scr_atr.append(tc["dir"] * (C[t] - tc["fill"]) / a - (2.0 * tick / a if tick else 0.0))
                resting.setdefault(model, {})[s] = dict(touches=n_touch, confirmed=n_conf,
                                                         conf_atr=conf_atr, scr_atr=scr_atr)
        for sg in sigs:
            row = per_sig[id(sg)]
            row.update(symbol=s, entry_time=iso(D["T"][sg["t0"]]), span=sg["t0"] - sg["a"],
                       quarter=quarter(D["T"][sg["t0"]]), **features(D, sg))
            rows.append(row)
        took = {(r["t0"], r["dir"]): r for r in rows if r["symbol"] == s and r["why_engine"] != "skipped"}
        engine_check["engine_trades"] += len(eng)
        engine_check["reproduced"] += sum(1 for k, x in eng_keys.items()
                                          if k in took and abs(took[k]["gross_engine"] - x["R"]) < 1e-4)
        print(f"{s:5s} {len(sigs):5d} candidates, harness took {len(took):5d}"
              + (f", engine took {len(eng):5d}" if fill == "intrabar" else ""))

    # ---- write per signal table
    cols = ["symbol", "entry_time", "dir", "kind", "touches", "span", "stop_src", "entry", "stop0", "risk_atr",
            "d_e21", "d_e50", "d_e200", "room", "mom5", "mom20", "ext_1y", "ext_5y", "atr_ratio", "hour", "dow",
            "mfe", "gross_engine"] + [f"R_{e}" for e in EXITS] + [f"why_{e}" for e in EXITS] + ["R_fade", "why_fade", "quarter"]
    with open(os.path.join(OUT, "signals.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    # ---- report
    L = []
    L.append(f"# Exit, filter and band fade study on the frozen engine's entries (fill = {fill})\n")
    L.append("Entry bar features (EMA distances, momentum, room) are measured at the entry bar's close. "
             + ("With intrabar fills that close comes AFTER the fill, so those filters contain lookahead "
                "and are for reference only; the `next` fill run is the decision basis.\n"
                if fill == "intrabar" else
                "With next bar fills the close is known before the fill, so the filters are usable live.\n"))
    if fill == "intrabar":
        L.append(f"Harvested candidates: {len(rows)}. Engine trades reproduced exactly by the harness: "
                 f"{engine_check['reproduced']}/{engine_check['engine_trades']}.\n")
    else:
        L.append(f"Harvested candidates: {len(rows)}. Trigger: intrabar touch (as the live bot runs it), "
                 f"fill: next bar open. The harvest is validated by the intrabar run's self check.\n")
    L.append(f"Preregistered tests: {N_TESTS}. One sided Bonferroni threshold on the bootstrap t: **{Z_CRIT:.2f}**. "
             f"Costs: 2 ticks per round trip. Bootstrap: {BOOT_REPS} resamples of calendar quarters.\n")

    eng_rows = [r for r in rows if r["why_engine"] != "skipped"]
    eng_by_key = {(r["symbol"], r["entry_time"]): r for r in eng_rows}

    L.append("## Exit variants (each on its own non overlapping trade set)\n")
    L.append("| variant | trades | avgR net | win% | PF | total R | boot t | paired diff vs engine | paired t | verdict |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for name in EXITS:
        vr = [r for r in rows if r[f"why_{name}"] != "skipped"]
        rs = [r[f"R_{name}"] for r in vr]; qs = [r["quarter"] for r in vr]
        sm = summarize(rs); m, t = block_t(rs, qs)
        if name == "engine":
            L.append(f"| {name} | {sm['n']} | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {sm['totalR']:+.0f} | {t:.2f} | | | reference |")
            continue
        pairs = [(r[f"R_{name}"] - eng_by_key[(r['symbol'], r['entry_time'])]["R_engine"], r["quarter"])
                 for r in vr if (r["symbol"], r["entry_time"]) in eng_by_key]
        dm, dt = block_t([p[0] for p in pairs], [p[1] for p in pairs])
        verdict = "PASS" if dt > Z_CRIT else ("worse" if dm < 0 else "no")
        L.append(f"| {name} | {sm['n']} | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {sm['totalR']:+.0f} | {t:.2f} | {dm:+.4f} ({len(pairs)} paired) | {dt:.2f} | {verdict} |")

    L.append("\n## Filters on the engine's trades (in vs out)\n")
    L.append("| filter | rule | in: n, avgR, win% | out: n, avgR, win% | diff | boot t | verdict |")
    L.append("|---|---|---|---|---|---|---|")
    for fname, (feat, op, val) in FILTERS.items():
        def keep(r):
            x = r[feat]
            if op == ">=": return x >= val
            if op == "<=": return x <= val
            if op == "in": return val[0] <= x <= val[1]
        inn = [r for r in eng_rows if keep(r)]; out = [r for r in eng_rows if not keep(r)]
        si, so = summarize([r["R_engine"] for r in inn]), summarize([r["R_engine"] for r in out])
        # difference statistic: resample quarters of the full set, recompute avgR_in - avgR_out
        by_q = defaultdict(list)
        for r in eng_rows: by_q[r["quarter"]].append((r["R_engine"], keep(r)))
        keys = list(by_q); rng = np.random.default_rng(SEED); diffs = []
        for _ in range(BOOT_REPS):
            pick = rng.integers(0, len(keys), len(keys))
            a = [v for i in pick for v, k in by_q[keys[i]] if k]; b = [v for i in pick for v, k in by_q[keys[i]] if not k]
            if a and b: diffs.append(np.mean(a) - np.mean(b))
        diff = si["avgR"] - so["avgR"]; sd = float(np.std(diffs)) if diffs else float("nan")
        tdiff = diff / sd if sd and sd > 0 else float("nan")
        share = si["n"] / max(1, len(eng_rows))
        verdict = "PASS" if (tdiff > Z_CRIT and share >= 0.25) else ("too few kept" if tdiff > Z_CRIT else "no")
        L.append(f"| {fname} | {feat} {op} {val} | {si['n']}, {si['avgR']:+.4f}, {si['win']:.0f}% | "
                 f"{so['n']}, {so['avgR']:+.4f}, {so['win']:.0f}% | {diff:+.4f} | {tdiff:.2f} | {verdict} |")

    L.append("\n## Band fade (trade against breaks that fire with little room to the band; "
             "2 tick cost charged, one fade at a time per instrument)\n")
    L.append("| room threshold | fade trades | avgR | win% | PF | boot t | verdict | (engine avgR on same signals) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for th in FADE_THRESHOLDS:
        sub = [r for r in rows if r["room"] < th and r["R_fade"] != ""]
        rs = [r["R_fade"] for r in sub]; qs = [r["quarter"] for r in sub]
        sm = summarize(rs); m, t = block_t(rs, qs)
        same = [r["R_engine"] for r in sub if r["why_engine"] != "skipped"]
        verdict = "PASS" if t > Z_CRIT else "no"
        L.append(f"| room < {th} | {sm['n']} | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {t:.2f} | {verdict} | "
                 f"{np.mean(same):+.4f} on {len(same)} |" if same else
                 f"| room < {th} | {sm['n']} | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {t:.2f} | {verdict} | n/a |")

    if resting:
        L.append("\n## Resting order model (fill at the line, scratch at that bar's close if the engine does not confirm)\n")
        L.append("naive = a stop order on every line that could be touched; prequalified = only lines whose refit "
                 "geometry and stop already pass on data through the previous bar. All P&L in ATR units, net of 2 ticks.\n")
        L.append("| model | touches | confirmed | confirmed avg (ATR) | scratched avg (ATR) | **per touch (ATR)** | total (ATR) |")
        L.append("|---|---|---|---|---|---|---|")
        for model, per in resting.items():
            tt = sum(v["touches"] for v in per.values()); cc = sum(v["confirmed"] for v in per.values())
            ca = [x for v in per.values() for x in v["conf_atr"]]; sa = [x for v in per.values() for x in v["scr_atr"]]
            tot = np.sum(ca) + np.sum(sa)
            L.append(f"| {model} | {tt} | {cc} ({cc / max(1, tt):.0%}) | {np.mean(ca) if ca else 0:+.4f} | "
                     f"{np.mean(sa) if sa else 0:+.4f} | {tot / max(1, tt):+.4f} | {tot:+.0f} |")
        L.append("\nThe confirmed trades are the engine's own trades, scored at the line. A positive per touch "
                 "number means resting orders recover the intrabar edge after paying for the scratches.\n")
    L.append("\n## Feature summary on the engine's trades (avgR by quartile)\n")
    L.append("| feature | Q1 (low) | Q2 | Q3 | Q4 (high) |")
    L.append("|---|---|---|---|---|")
    for feat in ["room", "d_e21", "d_e50", "d_e200", "mom5", "mom20", "ext_1y", "ext_5y", "atr_ratio", "risk_atr", "touches", "span"]:
        xs = np.array([r[feat] for r in eng_rows], float); rs = np.array([r["R_engine"] for r in eng_rows], float)
        qs = np.quantile(xs, [0.25, 0.5, 0.75]); cells = []
        bins = [xs <= qs[0], (xs > qs[0]) & (xs <= qs[1]), (xs > qs[1]) & (xs <= qs[2]), xs > qs[2]]
        for b in bins: cells.append(f"{rs[b].mean():+.3f} (n={b.sum()})" if b.sum() else "n/a")
        L.append(f"| {feat} | " + " | ".join(cells) + " |")

    open(os.path.join(OUT, "report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n-> {OUT}/report.md and {OUT}/signals.csv")


if __name__ == "__main__":
    main()
