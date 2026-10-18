#!/usr/bin/env python3
"""Supply and demand zones on intraday bars: Adam's discretionary setup written as
rules, with his Notion strategy reference and NQ trade log folded in.

Zone (demand; supply is the mirror), found and traded on the same timeframe (the
log shows 5m zones in 127 of 128 taken trades):
  consolidation  the 6 bars ending at the zone candle span <= CONS x ATR
  zone candle    the last bearish bar before the spike (the next bar is bullish),
                 range >= 3 ticks; zone = wick to wick
  spike          within the next 6 bars a close rises >= SPIKE x the zone candle's
                 range above its close; the zone goes live at that bar (no lookahead)
  life           tappable any number of times until a bar closes through its far
                 side; zones more than 30 ATR from price are dropped
  approach       each of the 6 bars up to and including the touch spans <= APPROACH
                 x ATR (the log's slow selloff/pump and consolidation approaches;
                 crash/pump approaches lost in the log)
  rejection      a bar that trades into the zone and closes back above its top
  entry          next bar's open; stop = zone low - max(3 ticks, 0.15 ATR); 1R = entry - stop
  target         nearest live supply zone whose bottom is >= 1R away, 3R if none within 10R

Simulated grid: SPIKE {2,3} x CONS {2,3} x APPROACH {1.5,2.5} ATR.
Variants recorded per trade and applied afterwards (every combination is a config):
  manage    fixed stop (reference page: the stop does not move) | stop to entry at +1R (verbal rule)
  target    nearest | further (second nearest zone) | rr1.5 (nearest zone if >= 1.5R, else further, else skip)
  fresh     any tap | first touch only (reference page; 115 of 128 logged trades were fresh)
  age       any | zone younger than 2 sessions (reference page)
  bias      none | not both HTF (4h EMA50) and 15m EMA50 against (verbal rule) | HTF with
            (EMA gates were rejected by Adam before; "with trend" in the log is his own read)
  parabolic off | no continuation entry while the trading tf close is > 3.5 ATR from its 21 EMA
            in the trade's direction, cleared at 2 ATR (shorts at supply after a pump stay allowed)
  session   all | NY AM only (09:30 to 12:00 ET) | all but NY PM (12:00 to 16:45 ET) | ex_hours (entry hours whose
            exploration avgR is positive with 100+ trades for that config, chosen before validation and holdout)
Every config is also scored flat at 16:45 ET of the entry session (prop firm version).

Notion NQ trade log, taken trades 2026-07-03 to 2026-10-15 (128: 62 W, 54 L, 12 BE), avg +0.28R, t 2.4, no costs:
  with trend +0.50R (68) vs against 0.00R (60); NY AM +0.37 (61), Asian +0.34 (50), NY PM -0.32 (13), London (4)
  approach: slow +0.42 (43), consolidation +0.28 (16), break and retest +0.49 (10), crash/pump -0.16 (28)
  zone tf 5m in 127 of 128; fresh zone in 115 of 128.
The report also prints Adam's stated config (spike 2, cons 2, approach 1.5, BE at 1R, nearest target, fresh
only, not both biases against, parabolic on, all sessions) on exploration and validation, and the engine's
NQ trades over the log window for a side by side with the log (a two month peek at one instrument).

Costs: COMM per side plus a tick on stop, BE and time exits. When a bar hits both the stop and a target the
stop is taken (conservative; the bars are 5m or 15m so the order inside the bar is unknown). Explore 2008 to
2014, validate 2015 to 2016, one holdout look per timeframe (5m primary, 15m second): best validation among
the top 10 exploration configs out of 3456 (8 grid x 432 variant combinations); the luck baseline is printed.
Driftless random walk check: every config lands at minus costs (about -0.10 to -0.16R).

Usage (repo folder):  python3 research_sd.py DATA_DIR_1m [--tf 5 15] [--symbols ...]
Writes research/sd_report.md, research/sd_trades_<tf>m.npz (everything), research/sd_chosen_<tf>m.csv
(holdout, flat version, for prop_sim.py --trades) and research/sd_nq_logwindow_<tf>m.csv.
"""
import os, sys, csv, math, glob, re, time, itertools
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

from instruments import TICKS

OUT = "research"
COMM = 1.5
EXPL_END, VAL_END = 2015, 2017
BOOT_REPS, SEED = 300, 17
FLAT_MIN = 16 * 60 + 45
SESSION_MIN = 23 * 60
NY_AM, NY_PM = (9 * 60 + 30, 12 * 60), (12 * 60, FLAT_MIN)
GRID = dict(spike=[2.0, 3.0], cons=[2.0, 3.0], approach=[1.5, 2.5])
VARIANTS = dict(manage=["fixed", "be"], target=["nearest", "further", "rr1.5"], fresh=[0, 1], age=[0, 1],
                bias=[0, 1, 2], parabolic=[0, 1], session=["all", "ny_am", "no_ny_pm", "ex_hours"])
MIN_HOUR_N = 100
STATED = dict(spike=2.0, cons=2.0, approach=1.5, manage="be", target="nearest", fresh=1, age=0, bias=1, parabolic=1, session="all")
LOG_WINDOW = ("2026-07-02", "2026-10-16")
MICROS = {"ES": ("MES", 5), "NQ": ("MNQ", 2), "RTY": ("M2K", 5), "YM": ("MYM", 0.5), "GC": ("MGC", 10), "SI": ("SIL", 1000),
          "HG": ("MHG", 2500), "CL": ("MCL", 100), "NG": ("QG", 2500), "E6": ("M6E", 12500), "A6": ("M6A", 10000),
          "B6": ("M6B", 6250), "J1": ("MJY", 1250000), "E1": ("MSF", 12500)}
SYMS = list(MICROS)
COLS = ["sym", "cfg", "t", "dir", "R_px", "R_unit", "r_x", "why_x", "ov_x", "j_x", "r_t1", "j_t1", "ov_t1", "r_be", "j_be", "ov_be",
        "r_flat", "j_flat", "tgt1_rr", "tgt2_rr", "taps", "age", "sessmin", "htf", "b15", "para"]
I = {c: k for k, c in enumerate(COLS)}
WHY = {0: "stop", 1: "target", 2: "end", 3: "target", 4: "be", 5: "flat"}


def load_1m(path):
    ts, o, h, l, c, v = [], [], [], [], [], []; day_cache = {}
    with open(path) as f:
        for line in f:
            p = line.split(",")
            if len(p) < 6: continue
            d = p[0][:10]; base = day_cache.get(d)
            if base is None:
                base = int(datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), tzinfo=timezone.utc).timestamp()); day_cache[d] = base
            ts.append(base + int(p[0][11:13]) * 3600 + int(p[0][14:16]) * 60)
            o.append(float(p[1])); h.append(float(p[2])); l.append(float(p[3])); c.append(float(p[4])); v.append(float(p[5]))
    return np.array(ts, np.int64), np.array(o), np.array(h), np.array(l), np.array(c), np.array(v)


def resample(T, O, H, L, C, V, tf):
    if tf == 1: return T, O, H, L, C, V
    sess = (T - 60 + 6 * 3600) // 86400; off = (T - 60 + 6 * 3600) % 86400
    key = sess * 100000 + off // (tf * 60)
    idx = np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]])); ends = np.concatenate([idx[1:], [len(T)]]) - 1
    return T[ends], O[idx], np.maximum.reduceat(H, idx), np.minimum.reduceat(L, idx), C[ends], np.add.reduceat(V, idx)


def ema(x, n):
    out = np.empty(len(x)); a = 2.0 / (n + 1); out[0] = x[0]
    for i in range(1, len(x)): out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(H, L, C, n=14):
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
    return ema(tr, 2 * n - 1)


def bias_series(raw, tf_bias, T_trade):
    """sign(close - EMA50) of the last COMPLETED tf_bias bar before each trading bar's end."""
    Tb, Ob, Hb, Lb, Cb, Vb = resample(*raw, tf_bias); e = ema(Cb, 50); s = np.sign(Cb - e)
    idx = np.searchsorted(Tb, T_trade, side="right") - 1
    return np.where(idx >= 0, s[np.clip(idx, 0, len(s) - 1)], 0.0)


def simulate(sym_id, bars, tf, cfg_id, spike_mult, cons_atr, appr_atr, tick, mult, htf, b15):
    """One pass per config. The simulated position is the longest path (fixed stop, further
    target); nearest target, BE and 16:45 flat exits are recorded as events so every variant
    is scored from the same pass. Returns a float array, one row per trade (COLS)."""
    T, O, H, L, C, V = bars; n = len(T)
    A = atr(H, L, C); e21 = ema(C, 21); mod = ((T // 60) % 1440).astype(int)
    sess = (T - 60 + 6 * 3600) // 86400
    rng6 = H - L
    span6 = np.full(n, np.inf); span6[5:] = swv(H, 6).max(axis=1) - swv(L, 6).min(axis=1)
    rmax6 = np.zeros(n); rmax6[5:] = swv(rng6, 6).max(axis=1)
    # zone births: candle i qualifies when the spike is confirmed at bar i + 1 + k (k < 6)
    m = n - 6; W = swv(C[1:], 6)[:m]
    up = (W - C[:m, None]) >= spike_mult * rng6[:m, None]; dn = (C[:m, None] - W) >= spike_mult * rng6[:m, None]
    kup = np.where(up.any(1), up.argmax(1), -1); kdn = np.where(dn.any(1), dn.argmax(1), -1)
    ok = (rng6[:m] >= 3 * tick) & (span6[:m] <= cons_atr * A[:m]) & (np.arange(m) >= 60)
    bear = ok & (C[:m] < O[:m]) & (C[1:m + 1] >= O[1:m + 1]) & (kup >= 0)
    bull = ok & (C[:m] > O[:m]) & (C[1:m + 1] <= O[1:m + 1]) & (kdn >= 0)
    births = defaultdict(list)
    for i in np.flatnonzero(bear): births[i + 1 + kup[i]].append((1, L[i], H[i]))
    for i in np.flatnonzero(bull): births[i + 1 + kdn[i]].append((-1, L[i], H[i]))
    demand, supply = [], []
    pos = None; pending = None; out = []; para_block = {1: False, -1: False}

    def close_out(p, j, px, why):
        d = p["dir"]; R = p["R"]; cost = 2 * COMM / (R * mult); r = lambda x: (x - p["entry"]) * d / R - cost
        out.append((sym_id, cfg_id, T[p["i0"]], d, R, R * mult, r(px), why, int(sess[j] != p["sess"]), j - p["i0"],
                    r(p["t1_px"]) if p["t1_j"] >= 0 else r(px), p["t1_j"] - p["i0"] if p["t1_j"] >= 0 else -1, p["t1_ov"],
                    r(p["be_px"]) if p["be_j"] >= 0 else r(px), p["be_j"] - p["i0"] if p["be_j"] >= 0 else -1, p["be_ov"],
                    r(p["flat_px"]) if p["flat_j"] >= 0 else r(px), p["flat_j"] - p["i0"] if p["flat_j"] >= 0 else -1,
                    p["tgt1_rr"], p["tgt2_rr"], p["taps"], p["age"], mod[p["i0"]], p["htf"], p["b15"], p["para"]))

    for j in range(60, n):
        a = A[j - 1] if A[j - 1] > 0 else 1e-12
        if C[j] > e21[j] + 3.5 * a: para_block[1] = True
        elif C[j] <= e21[j] + 2.0 * a: para_block[1] = False
        if C[j] < e21[j] - 3.5 * a: para_block[-1] = True
        elif C[j] >= e21[j] - 2.0 * a: para_block[-1] = False
        # ---- pending entry fills at this open
        if pending is not None:
            d, z, stop, taps, age = pending; pending = None
            entry = O[j]; R = (entry - stop) * d
            if R > 0:
                if d > 0: opp = sorted(x["lo"] for x in supply if entry + R <= x["lo"] <= entry + 10 * R)
                else: opp = sorted((x["hi"] for x in demand if entry - 10 * R <= x["hi"] <= entry - R), reverse=True)
                tgt1 = opp[0] if opp else entry + d * 3 * R; tgt2 = opp[1] if len(opp) > 1 else tgt1
                pos = dict(dir=d, entry=entry, stop=stop, R=R, tgt1=tgt1, tgt2=tgt2, tgt1_rr=(tgt1 - entry) * d / R, tgt2_rr=(tgt2 - entry) * d / R,
                           i0=j, sess=sess[j], armed=False, t1_j=-1, t1_px=0.0, t1_ov=0, be_j=-1, be_px=0.0, be_ov=0, flat_j=-1, flat_px=0.0,
                           taps=taps, age=age, htf=float(htf[j]), b15=float(b15[j]), para=int(para_block[d]))
        # ---- manage the position (events first, then the primary exit)
        if pos is not None:
            p = pos; d = p["dir"]; ov = int(sess[j] != p["sess"])
            if p["armed"] and p["be_j"] < 0 and ((d > 0 and L[j] <= p["entry"]) or (d < 0 and H[j] >= p["entry"])):
                gap = (d > 0 and O[j] < p["entry"]) or (d < 0 and O[j] > p["entry"])
                p["be_j"] = j; p["be_px"] = (O[j] if gap else p["entry"]) - d * tick; p["be_ov"] = ov
            stopped = (d > 0 and L[j] <= p["stop"]) or (d < 0 and H[j] >= p["stop"])     # stop before target when both hit in a bar
            if not stopped and p["t1_j"] < 0 and ((d > 0 and H[j] >= p["tgt1"]) or (d < 0 and L[j] <= p["tgt1"])):
                p["t1_j"] = j; p["t1_px"] = p["tgt1"]; p["t1_ov"] = ov
            if stopped:
                gap = (d > 0 and O[j] < p["stop"]) or (d < 0 and O[j] > p["stop"])
                close_out(p, j, (O[j] if gap else p["stop"]) - d * tick, 0); pos = None
            elif (d > 0 and H[j] >= p["tgt2"]) or (d < 0 and L[j] <= p["tgt2"]):
                close_out(p, j, p["tgt2"], 1); pos = None
            else:
                if not p["armed"] and ((d > 0 and H[j] >= p["entry"] + p["R"]) or (d < 0 and L[j] <= p["entry"] - p["R"])): p["armed"] = True
                if p["flat_j"] < 0 and sess[j] == p["sess"] and (mod[j] >= FLAT_MIN or j == n - 1 or sess[j + 1] != p["sess"]):
                    p["flat_j"] = j; p["flat_px"] = C[j] - d * tick
        # ---- zones: invalidation on this close, distance pruning, births
        demand = [z for z in demand if C[j] >= z["lo"] and z["hi"] >= C[j] - 30 * a]
        supply = [z for z in supply if C[j] <= z["hi"] and z["lo"] <= C[j] + 30 * a]
        for side, lo, hi in births.get(j, ()):
            (demand if side > 0 else supply).append(dict(lo=lo, hi=hi, taps=0, born=j))
        # ---- rejection at this bar (then count taps)
        if pos is None and pending is None and mod[j] < FLAT_MIN - 5 and rmax6[j] <= appr_atr * a:
            for z in sorted(demand, key=lambda z: -z["hi"]):
                if L[j] <= z["hi"] and C[j] > z["hi"]:
                    pending = (1, z, z["lo"] - max(3 * tick, 0.15 * a), z["taps"], j - z["born"]); break
            if pending is None:
                for z in sorted(supply, key=lambda z: z["lo"]):
                    if H[j] >= z["lo"] and C[j] < z["lo"]:
                        pending = (-1, z, z["hi"] + max(3 * tick, 0.15 * a), z["taps"], j - z["born"]); break
        for z in demand:
            if L[j] <= z["hi"]: z["taps"] += 1
        for z in supply:
            if H[j] >= z["lo"]: z["taps"] += 1
    if pos is not None: close_out(pos, n - 1, C[n - 1] - pos["dir"] * tick, 2)
    return np.array(out, dtype=float).reshape(-1, len(COLS))


# ---------------------------------------------------------------- scoring (vectorised)
def outcome(D, manage, target, flat):
    """Per trade result for one management/target variant: (valid mask, R, why code, overnight)."""
    j = D[:, I["j_x"]] + 0.2; r = D[:, I["r_x"]].copy(); why = D[:, I["why_x"]].copy(); ov = D[:, I["ov_x"]].copy()
    valid = np.ones(len(D), bool); use_t1 = np.ones(len(D), bool)
    if target == "further": use_t1[:] = False
    elif target == "rr1.5":
        use_t1 = D[:, I["tgt1_rr"]] >= 1.5; valid = use_t1 | (D[:, I["tgt2_rr"]] >= 1.5)
    t1 = use_t1 & (D[:, I["j_t1"]] >= 0)
    j = np.where(t1, D[:, I["j_t1"]] + 0.1, j); r = np.where(t1, D[:, I["r_t1"]], r); why = np.where(t1, 3, why); ov = np.where(t1, D[:, I["ov_t1"]], ov)
    if manage == "be":
        be = (D[:, I["j_be"]] >= 0) & (D[:, I["j_be"]] < j)
        j = np.where(be, D[:, I["j_be"]], j); r = np.where(be, D[:, I["r_be"]], r); why = np.where(be, 4, why); ov = np.where(be, D[:, I["ov_be"]], ov)
    if flat:
        fl = (D[:, I["j_flat"]] >= 0) & (D[:, I["j_flat"]] < j)
        r = np.where(fl, D[:, I["r_flat"]], r); why = np.where(fl, 5, why); ov = np.where(fl, 0, ov)
    return valid, r, why, ov


def fmask(D, fresh, age, bias, parabolic, session, age_cap):
    m = np.ones(len(D), bool); d = D[:, I["dir"]]; sm = D[:, I["sessmin"]]
    if bias == 1: m &= ~((D[:, I["htf"]] * d < 0) & (D[:, I["b15"]] * d < 0))
    elif bias == 2: m &= D[:, I["htf"]] * d > 0
    if parabolic: m &= D[:, I["para"]] == 0
    if fresh: m &= D[:, I["taps"]] == 0
    if age: m &= D[:, I["age"]] <= age_cap
    if session == "ny_am": m &= (sm >= NY_AM[0]) & (sm < NY_AM[1])
    elif session == "no_ny_pm": m &= ~((sm >= NY_PM[0]) & (sm < NY_PM[1]))
    return m


def ex_hours(D, bv, r, ex_m):
    """Entry hours (ET) with positive exploration avgR and MIN_HOUR_N+ trades for this base config -> (hour list, mask)."""
    hour = (D[:, I["sessmin"]] // 60).astype(int); e = bv & ex_m
    sums = np.bincount(hour[e], weights=r[e], minlength=24); cnt = np.bincount(hour[e], minlength=24)
    keep = [h for h in range(24) if cnt[h] >= MIN_HOUR_N and sums[h] / cnt[h] > 0]
    return keep, np.isin(hour, keep)


def hour_table(L, D, r, m_ex, m_ho, label, b="holdout"):
    hour = (D[:, I["sessmin"]] // 60).astype(int)
    L += [f"\nBy entry hour (ET), {label}:\n", f"| hour | explore n | explore avgR | {b} n | {b} avgR |", "|---|---|---|---|---|"]
    for h in range(24):
        e = m_ex & (hour == h); o = m_ho & (hour == h)
        if e.any() or o.any():
            L.append(f"| {h:02d} | {e.sum()} | {r[e].mean() if e.any() else float('nan'):+.4f} | {o.sum()} | {r[o].mean() if o.any() else float('nan'):+.4f} |")


def stats(r, mcode):
    if len(r) == 0: return dict(n=0, m=float("nan"), t=float("nan"), win=float("nan"))
    keys, inv = np.unique(mcode, return_inverse=True); K = len(keys)
    sums = np.bincount(inv, weights=r, minlength=K); cnts = np.bincount(inv, minlength=K).astype(float)
    picks = np.random.default_rng(SEED).integers(0, K, (BOOT_REPS, K))
    means = sums[picks].sum(1) / cnts[picks].sum(1); m = float(r.mean()); sd = float(means.std())
    return dict(n=len(r), m=m, t=m / sd if sd > 0 else float("nan"), win=float((r > 0).mean() * 100))


def cfg_label(c):
    return dict(spike=c[0], cons=c[1], approach=c[2], manage=c[3], target=c[4], fresh=c[5], age=c[6], bias=c[7], parabolic=c[8], session=c[9])


def select(D, cfg, grid, age_cap):
    """Mask and per trade results (hold and flat) for one full config tuple."""
    spike, cons, appr, manage, target, fresh, age, bias, para, session = cfg
    valid, r, why, ov = outcome(D, manage, target, False); _, rf, _, _ = outcome(D, manage, target, True)
    bv = (D[:, I["cfg"]] == grid.index((spike, cons, appr))) & valid
    m = bv & fmask(D, fresh, age, bias, para, session, age_cap)
    if session == "ex_hours": m &= ex_hours(D, bv, r, D[:, I["year"]] < EXPL_END)[1]
    return m, r, rf, why, ov


def score_tf(D, tf, syms, L):
    year = D[:, I["year"]]; mcode = D[:, I["mcode"]]; age_cap = 2 * SESSION_MIN / tf
    ex_m, va_m, ho_m = year < EXPL_END, (year >= EXPL_END) & (year < VAL_END), year >= VAL_END
    grid = list(itertools.product(GRID["spike"], GRID["cons"], GRID["approach"]))
    filt = [(f, fmask(D, *f, age_cap)) for f in itertools.product(VARIANTS["fresh"], VARIANTS["age"], VARIANTS["bias"], VARIANTS["parabolic"], VARIANTS["session"])]
    # ex_hours masks depend on the base config: fmask treats the session as "all"; the hour mask is added per (grid, manage, target)
    configs = []
    for gi, g in enumerate(grid):
        base = D[:, I["cfg"]] == gi
        for manage, target in itertools.product(VARIANTS["manage"], VARIANTS["target"]):
            valid, r, why, ov = outcome(D, manage, target, False); _, rf, _, _ = outcome(D, manage, target, True); bv = base & valid
            hmask = ex_hours(D, bv, r, ex_m)[1]
            for f, fm in filt:
                m = bv & fm
                if f[4] == "ex_hours": m &= hmask
                e, v = m & ex_m, m & va_m
                configs.append(dict(cfg=(g[0], g[1], g[2], manage, target) + f, ex=stats(r[e], mcode[e]), exf=stats(rf[e], mcode[e]),
                                    va=stats(r[v], mcode[v]), vaf=stats(rf[v], mcode[v])))
    valid = [c for c in configs if c["ex"]["n"] >= 300]
    names = list(cfg_label(configs[0]["cfg"]))
    L += [f"\n## {tf} minute bars: {len(configs)} configs, {len(valid)} with 300+ exploration trades; "
          f"{sum(1 for c in valid if c['ex']['m'] > 0)} positive on exploration, {sum(1 for c in valid if c['va']['n'] >= 50 and c['va']['m'] > 0)} positive on validation "
          f"(flat version: {sum(1 for c in valid if c['exf']['m'] > 0)} / {sum(1 for c in valid if c['va']['n'] >= 50 and c['vaf']['m'] > 0)})\n",
          "| " + " | ".join(names) + " | n explore | avgR explore | t | n validate | avgR validate | flat explore | flat validate |", "|" + "---|" * (len(names) + 7)]
    top = sorted(valid, key=lambda c: -c["ex"]["m"])[:10]
    for c in top:
        L.append("| " + " | ".join(str(x) for x in c["cfg"]) + f" | {c['ex']['n']} | {c['ex']['m']:+.4f} | {c['ex']['t']:.2f} | {c['va']['n']} | "
                 f"{c['va']['m']:+.4f} | {c['exf']['m']:+.4f} | {c['vaf']['m']:+.4f} |")
    # Adam's stated config, exploration and validation only
    st = next((c for c in configs if cfg_label(c["cfg"]) == STATED), None)
    if st:
        L.append(f"\nAdam's stated config {STATED}: explore {st['ex']['n']} trades avgR {st['ex']['m']:+.4f} (t {st['ex']['t']:.2f}, win {st['ex']['win']:.0f}%), "
                 f"validate {st['va']['n']} trades avgR {st['va']['m']:+.4f}; flat version {st['exf']['m']:+.4f} / {st['vaf']['m']:+.4f}.")
        m_st, r_st, _, _, _ = select(D, st["cfg"], grid, age_cap)
        hour_table(L, D, r_st, m_st & ex_m, m_st & va_m, "stated config (holdout not read)", "validate")
    chosen = None
    if top:
        chosen = max(top, key=lambda c: (c["va"]["m"] if c["va"]["n"] >= 50 else -9))
        m, r, rf, why, ov = select(D, chosen["cfg"], grid, age_cap)
        hour_table(L, D, r, m & ex_m, m & ho_m, "chosen config"); m &= ho_m
        r, rf, why, ov = r[m], rf[m], why[m], ov[m]; H = D[m]
        s_, sf = stats(r, mcode[m]), stats(rf, mcode[m])
        L.append(f"\n**Chosen {cfg_label(chosen['cfg'])}: holdout 2017 to 2026, {s_['n']} trades, net avgR {s_['m']:+.4f}, t {s_['t']:.2f}, win {s_['win']:.0f}% "
                 f"-> {'PASS' if (s_['n'] and s_['m'] > 0 and s_['t'] > 2.0) else 'no'}; flat version avgR {sf['m']:+.4f}, t {sf['t']:.2f} "
                 f"-> {'PASS' if (sf['n'] and sf['m'] > 0 and sf['t'] > 2.0) else 'no'}**\n")
        if len(r):
            for code in (0, 3, 1, 4, 2):
                sub = why == code
                if sub.any(): L.append(f"- exits by {WHY[code]}{' (further)' if code == 1 else ''}: {sub.sum()} ({sub.mean():.0%}), avgR {r[sub].mean():+.3f}")
            L.append(f"- overnight holds: {ov.mean() * 100:.0f}%; trades per instrument per year: {len(r) / max(1, len(set(H[:, I['sym']]))) / 9.7:.0f}; "
                     f"median bars held {np.median(H[:, I['j_x']]):.0f}")
            L.append("- by year: " + ", ".join(f"{int(y)}: {r[year[m] == y].mean():+.3f} (n={(year[m] == y).sum()})" for y in np.unique(year[m])))
            sm = H[:, I["sessmin"]]
            sessions = {"Asian 18:00-03:00": (sm >= 18 * 60) | (sm < 3 * 60), "London 03:00-09:30": (sm >= 3 * 60) & (sm < NY_AM[0]),
                        "NY AM": (sm >= NY_AM[0]) & (sm < NY_AM[1]), "NY PM": (sm >= NY_PM[0]) & (sm < NY_PM[1])}
            L.append("- by entry session: " + ", ".join(f"{k}: {r[v].mean():+.3f} (n={v.sum()})" for k, v in sessions.items() if v.any()))
            fr = H[:, I["taps"]] == 0; wt = H[:, I["htf"]] * H[:, I["dir"]] > 0
            L.append(f"- fresh zones: {r[fr].mean() if fr.any() else float('nan'):+.3f} (n={fr.sum()}), tapped before: {r[~fr].mean() if (~fr).any() else float('nan'):+.3f} (n={(~fr).sum()}); "
                     f"HTF with: {r[wt].mean() if wt.any() else float('nan'):+.3f} (n={wt.sum()}), HTF against or flat: {r[~wt].mean() if (~wt).any() else float('nan'):+.3f} (n={(~wt).sum()})")
            L += ["", "| instrument | trades | net avgR | t | win% | flat avgR |", "|---|---|---|---|---|---|"]
            for k, sym in enumerate(syms):
                s2 = H[:, I["sym"]] == k
                if s2.any():
                    a_, b_ = stats(r[s2], mcode[m][s2]), stats(rf[s2], mcode[m][s2])
                    L.append(f"| {sym} | {a_['n']} | {a_['m']:+.4f} | {a_['t']:.2f} | {a_['win']:.0f}% | {b_['m']:+.4f} |")
            write_trades(os.path.join(OUT, f"sd_chosen_{tf}m.csv"), H, rf, why, syms, tf)
    # NQ over the Notion log window, stated config, hold version (a peek at two months of one instrument)
    if st and "NQ" in syms:
        t0 = datetime.strptime(LOG_WINDOW[0], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp(); t1 = datetime.strptime(LOG_WINDOW[1], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        m, r, rf, why, ov = select(D, st["cfg"], grid, age_cap)
        m &= (D[:, I["sym"]] == syms.index("NQ")) & (D[:, I["t"]] >= t0) & (D[:, I["t"]] < t1)
        if m.any():
            r = r[m]
            L.append(f"\nNQ over the log window {LOG_WINDOW[0]} to {LOG_WINDOW[1]}, stated config: engine {m.sum()} trades, avgR {r.mean():+.3f}, win {(r > 0).mean() * 100:.0f}% "
                     f"(longs {(D[m, I['dir']] > 0).sum()}, shorts {(D[m, I['dir']] < 0).sum()}); log 128 taken trades, avgR +0.28 before costs. "
                     f"Trade list in sd_nq_logwindow_{tf}m.csv.")
            write_trades(os.path.join(OUT, f"sd_nq_logwindow_{tf}m.csv"), D[m], r, why[m], syms, tf)
        else:
            L.append(f"\nNQ over the log window: no engine trades at the stated config (data may end before {LOG_WINDOW[0]}).")
    return chosen


def write_trades(path, H, r, why, syms, tf):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["session", "symbol", "micro", "tf", "entry_time", "dir", "R_px", "R_unit", "R", "pnl_usd", "why", "taps", "age", "htf", "b15"])
        for k in range(len(H)):
            sym = syms[int(H[k, I["sym"]])]; t = int(H[k, I["t"]])
            w.writerow([datetime.fromtimestamp(t + 6 * 3600, timezone.utc).strftime("%Y-%m-%d"), sym, MICROS[sym][0], tf,
                        datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M"), int(H[k, I["dir"]]), f"{H[k, I['R_px']]:.6g}",
                        f"{H[k, I['R_unit']]:.2f}", f"{r[k]:.4f}", f"{r[k] * H[k, I['R_unit']]:.2f}", WHY[int(why[k])], int(H[k, I["taps"]]),
                        int(H[k, I["age"]]), int(H[k, I["htf"]]), int(H[k, I["b15"]])])


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_sd.py DATA_DIR_1m [--tf 5 15] [--symbols ...]")
    tfs = [5, 15]; syms = list(MICROS)
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
    os.makedirs(OUT, exist_ok=True)
    grid = list(itertools.product(GRID["spike"], GRID["cons"], GRID["approach"]))
    parts = {tf: [] for tf in tfs}
    for k, sym in enumerate(syms):
        if sym not in cat: print(f"{sym}: no 1 minute file"); continue
        tick = TICKS.get(sym, 0.0); micro, mult = MICROS[sym]; raw = load_1m(cat[sym])
        for tf in tfs:
            bars = resample(*raw, tf); htf = bias_series(raw, 240, bars[0]); b15 = bias_series(raw, 15, bars[0] - (1 if tf == 15 else 0))
            for cid, (spike, cons, appr) in enumerate(grid):
                t0 = time.time(); D = simulate(k, bars, tf, cid, spike, cons, appr, tick, mult, htf, b15); parts[tf].append(D)
                print(f"{sym:4s} {tf:2d}m spike {spike} cons {cons} appr {appr}: {len(D):5d} trades, avgR fixed/further {D[:, I['r_x']].mean() if len(D) else 0:+.4f} ({time.time() - t0:.0f}s)", flush=True)
    L = ["# Supply and demand zones on intraday bars (CME micro universe)\n",
         "Rules, variants and the Notion log baseline are in the script header. Explore 2008 to 2014, validate 2015 to 2016, one holdout "
         "look per timeframe at the best validation config among the top 10 by exploration. Costs: commissions plus a tick on stop, BE "
         "and time exits. 'flat' = the same trades cut at 16:45 ET of the entry session (prop firm version).\n"]
    for tf in tfs:
        if not parts[tf]: continue
        D = np.concatenate(parts[tf]); t = D[:, I["t"]].astype("int64").astype("datetime64[s]")
        yr = t.astype("datetime64[Y]").astype(int) + 1970; mo = t.astype("datetime64[M]").astype(int) % 12
        D = np.column_stack([D, yr, yr * 12 + mo]); I["year"], I["mcode"] = len(COLS), len(COLS) + 1
        np.savez_compressed(os.path.join(OUT, f"sd_trades_{tf}m.npz"), D=D, cols=np.array(COLS + ["year", "mcode"]), syms=np.array(syms), grid=np.array(grid))
        t0 = time.time(); score_tf(D, tf, syms, L); print(f"{tf}m scored in {time.time() - t0:.0f}s", flush=True)
    open(os.path.join(OUT, "sd_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/sd_report.md, sd_trades_<tf>m.npz, sd_chosen_<tf>m.csv (prop_sim.py --trades), sd_nq_logwindow_<tf>m.csv")


if __name__ == "__main__":
    main()
