#!/usr/bin/env python3
"""VWAP band fade parameter search on one instrument, done so the result means
something: rank on 2008 to 2014, confirm on 2015 to 2016, test once on 2017 to
2026.

Grid: timeframe x entry band x stop distance x target x session filter x
higher timeframe bias, plus an ex_hours session variant per config: the entry
hours (ET) with positive exploration avgR and 100+ trades, chosen on exploration
only. The report shows the chosen config by entry hour, exploration beside holdout. Entry is a limit at the band (filled when touched),
levels from the previous bar's close, flat at 16:45 ET, no entries in the first
60 minutes or the last 15. Bias: shorts only when the prior session closed
below its VWAP, longs only when it closed above (fade with the prior day).
Arming: a side can trigger only if the previous bar closed inside the entry
band. Conservative intrabar rule: a bar that reaches both the entry and the
stop is a stop. Costs: COMM per side + a tick on stop and time exits.

Selection: top 10 by exploration net avgR (min 300 exploration trades), then
the best of those on the validation years, then ONE holdout look. The report
also shows how many grid configs are positive on exploration and on
validation, which is the baseline for luck.

Usage (repo folder):  python3 research_vwap_opt.py DATA_DIR_1m NG
Writes research/vwap_opt_<SYM>.md and research/vwap_opt_<SYM>_trades.csv (the chosen config's trades).
"""
import os, sys, csv, math, glob, re, itertools, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from instruments import TICKS

OUT = "research"
COMM = 1.5
MIN_BAND_TICKS = 3
WARMUP_MIN, FLAT_MIN, LAST_ENTRY_MIN = 60, 16 * 60 + 45, 16 * 60 + 30
EXPL_END, VAL_END = 2015, 2017            # explore < 2015, validate 2015 to 2016, holdout >= 2017
BOOT_REPS, SEED = 300, 13
MIN_HOUR_N = 100
MICROS = {"NG": ("QG", 2500), "GC": ("MGC", 10), "ES": ("MES", 5), "NQ": ("MNQ", 2), "CL": ("MCL", 100), "SI": ("SIL", 1000),
          "HG": ("MHG", 2500), "RTY": ("M2K", 5), "YM": ("MYM", 0.5), "E6": ("M6E", 12500), "A6": ("M6A", 10000),
          "B6": ("M6B", 6250), "J1": ("MJY", 1250000), "E1": ("MSF", 12500)}
GRID = dict(tf=[1, 5, 15], k_in=[2.0, 2.5, 3.0, 3.5], k_stop_add=[1.0, 1.5, 2.5], target=["vwap", "band1"],
            session=["all", "us", "overnight"], bias=[0, 1])


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


def precompute(bars, tf):
    """Per bar: session id, session end index, minutes since open, prev bar VWAP/SD (NaN where unknown), prior session bias."""
    T, O, H, L, C, V = bars; n = len(T)
    sess = (T - 60 + 6 * 3600) // 86400
    starts = np.concatenate([[0], np.flatnonzero(sess[1:] != sess[:-1]) + 1]); ends = np.concatenate([starts[1:], [n]]) - 1
    sess_end = np.empty(n, np.int64); j_in = np.empty(n, np.int64)
    for a, b in zip(starts, ends):
        sess_end[a:b + 1] = b; j_in[a:b + 1] = np.arange(b - a + 1)
    tp = (H + L + C) / 3.0; vol = np.maximum(V, 0.0)
    cv = np.zeros(n); cpv = np.zeros(n); cpv2 = np.zeros(n)
    for a, b in zip(starts, ends):
        cv[a:b + 1] = np.cumsum(vol[a:b + 1]); cpv[a:b + 1] = np.cumsum(tp[a:b + 1] * vol[a:b + 1]); cpv2[a:b + 1] = np.cumsum(tp[a:b + 1] ** 2 * vol[a:b + 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        vwap = cpv / cv; sd = np.sqrt(np.maximum(cpv2 / cv - vwap ** 2, 0.0))
    pvw = np.full(n, np.nan); psd = np.full(n, np.nan)
    pvw[1:] = vwap[:-1]; psd[1:] = sd[:-1]
    pvw[starts] = np.nan                                          # first bar of a session: no previous bar in session
    # prior session bias: +1 if it closed above its VWAP, -1 below
    bias = np.zeros(n)
    for k in range(1, len(starts)):
        pb = ends[k - 1]; b_ = 1.0 if C[pb] > vwap[pb] else -1.0
        bias[starts[k]:ends[k] + 1] = b_
    mod = ((T // 60) % 1440).astype(int)
    return dict(sess_end=sess_end, j_in=j_in, pvw=pvw, psd=psd, bias=bias, mod=mod, sess=sess)


def run_config(sym, bars, pre, tf, k_in, k_stop_add, target, session, bias_on, tick, mult):
    T, O, H, L, C, V = bars; n = len(T)
    pvw, psd, mod, j_in, sess_end, bias = pre["pvw"], pre["psd"], pre["mod"], pre["j_in"], pre["sess_end"], pre["bias"]
    k_stop = k_in + k_stop_add
    up = pvw + k_in * psd; dn = pvw - k_in * psd
    ok = np.isfinite(pvw) & (psd * k_in >= MIN_BAND_TICKS * tick) & (j_in * tf >= WARMUP_MIN) & (mod < LAST_ENTRY_MIN) & (mod >= 0)
    if session == "us": ok &= (mod >= 8 * 60 + 30) & (mod < 16 * 60)
    elif session == "overnight": ok &= (mod >= 18 * 60) | (mod < 8 * 60 + 30)
    prev_inside = np.zeros(n, bool); prev_inside[1:] = (C[:-1] < up[1:]) & (C[:-1] > dn[1:])
    touch_s = ok & prev_inside & (H >= up) & (O < up); touch_l = ok & prev_inside & (L <= dn) & (O > dn)
    if bias_on: touch_s &= bias < 0; touch_l &= bias > 0
    cand = np.flatnonzero(touch_s | touch_l)
    trades = []; busy_until = -1
    for i in cand:
        if i <= busy_until: continue
        d = -1 if touch_s[i] else 1
        entry = up[i] if d < 0 else dn[i]
        stop = pvw[i] + k_stop * psd[i] if d < 0 else pvw[i] - k_stop * psd[i]
        R = abs(stop - entry)
        if R <= 0: continue
        e = sess_end[i]
        if (d < 0 and H[i] >= stop) or (d > 0 and L[i] <= stop):          # entry bar reached the stop
            xi, xpx, why = i, stop - d * tick, "stop"
        else:
            sl = slice(i + 1, e + 1)
            if target == "vwap": tgt = pvw[sl]
            else: tgt = pvw[sl] + (psd[sl] if d < 0 else -psd[sl])
            hit_stop = (H[sl] >= stop) if d < 0 else (L[sl] <= stop)
            hit_tgt = (L[sl] <= tgt) if d < 0 else (H[sl] >= tgt)
            flat = mod[sl] >= FLAT_MIN
            any_ = hit_stop | hit_tgt | flat
            if not any_.any(): xi = e; xpx = C[e] - d * tick; why = "time"
            else:
                k = int(np.argmax(any_)); xi = i + 1 + k
                if hit_stop[k]:
                    gapped = (d < 0 and O[xi] > stop) or (d > 0 and O[xi] < stop); xpx = (O[xi] if gapped else stop) - d * tick; why = "stop"
                elif hit_tgt[k]: xpx = float(tgt[k]); why = "target"
                else: xpx = C[xi] - d * tick; why = "time"
        pnl = (xpx - entry) * d
        trades.append(dict(symbol=sym, i=int(i), session=datetime.fromtimestamp(int(T[e]), timezone.utc).strftime("%Y-%m-%d"),
                           entry_time=datetime.fromtimestamp(int(T[i]), timezone.utc).strftime("%Y-%m-%d %H:%M"), dir=d, entry=entry,
                           stop=stop, exit=xpx, why=why, R_px=R, R=pnl / R - 2 * COMM / (R * mult), pnl_usd=pnl * mult - 2 * COMM, R_unit=R * mult))
        busy_until = xi
    return trades


def block_t(rows):
    by = defaultdict(list)
    for r in rows: by[r["session"][:7]].append(r["R"])
    keys = list(by); rng = np.random.default_rng(SEED); means = []
    for _ in range(BOOT_REPS):
        pick = rng.integers(0, len(keys), len(keys)); means.append(np.mean([x for i in pick for x in by[keys[i]]]))
    m = float(np.mean([r["R"] for r in rows])); sd = float(np.std(means))
    return m, (m / sd if sd > 0 else float("nan"))


def main():
    if len(sys.argv) < 3: sys.exit("usage: python3 research_vwap_opt.py DATA_DIR_1m SYMBOL")
    ddir, sym = sys.argv[1], sys.argv[2]
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(ddir, "*_full_1min*"))}
    tick = TICKS.get(sym, 0.0); micro, mult = MICROS[sym]
    raw = load_1m(cat[sym]); per_tf = {}
    for tf in GRID["tf"]:
        bars = resample(*raw, tf); per_tf[tf] = (bars, precompute(bars, tf))
    results = []; t0 = time.time()
    combos = list(itertools.product(*GRID.values()))
    for ci, (tf, k_in, k_add, target, session, bias) in enumerate(combos):
        bars, pre = per_tf[tf]
        tr = run_config(sym, bars, pre, tf, k_in, k_add, target, session, bias, tick, mult)
        ex = [r for r in tr if int(r["session"][:4]) < EXPL_END]; va = [r for r in tr if EXPL_END <= int(r["session"][:4]) < VAL_END]
        ho = [r for r in tr if int(r["session"][:4]) >= VAL_END]
        results.append(dict(cfg=(tf, k_in, k_add, target, session, bias), n_ex=len(ex), m_ex=np.mean([r["R"] for r in ex]) if ex else np.nan,
                            n_va=len(va), m_va=np.mean([r["R"] for r in va]) if va else np.nan, trades=tr, ho=ho))
        if ci % 25 == 0: print(f"{ci}/{len(combos)} configs, {time.time() - t0:.0f}s", flush=True)
    # ex_hours variant: for each session=all config, keep the entry hours (ET) with positive exploration avgR and MIN_HOUR_N+ trades,
    # chosen on exploration only, then applied to validation and holdout (a trade dropped this way frees no slot for a later one)
    extra = []
    for r in results:
        if r["cfg"][4] != "all": continue
        by = defaultdict(list)
        for x in r["trades"]:
            if int(x["session"][:4]) < EXPL_END: by[int(x["entry_time"][11:13])].append(x["R"])
        hours = {h for h, v in by.items() if len(v) >= MIN_HOUR_N and np.mean(v) > 0}
        tr = [x for x in r["trades"] if int(x["entry_time"][11:13]) in hours]
        ex = [x for x in tr if int(x["session"][:4]) < EXPL_END]; va = [x for x in tr if EXPL_END <= int(x["session"][:4]) < VAL_END]
        ho = [x for x in tr if int(x["session"][:4]) >= VAL_END]
        extra.append(dict(cfg=r["cfg"][:4] + ("ex_hours",) + r["cfg"][5:], n_ex=len(ex), m_ex=np.mean([x["R"] for x in ex]) if ex else np.nan,
                          n_va=len(va), m_va=np.mean([x["R"] for x in va]) if va else np.nan, trades=tr, ho=ho, hours=sorted(hours)))
    results += extra
    valid = [r for r in results if r["n_ex"] >= 300 and np.isfinite(r["m_ex"])]
    n_pos_ex = sum(1 for r in valid if r["m_ex"] > 0); n_pos_va = sum(1 for r in valid if r["n_va"] >= 50 and r["m_va"] > 0)
    top = sorted(valid, key=lambda r: -r["m_ex"])[:10]
    chosen = max(top, key=lambda r: (r["m_va"] if r["n_va"] >= 50 else -9))
    ho = chosen["ho"]; m, t = block_t(ho) if ho else (float("nan"), float("nan"))
    names = list(GRID)
    L = [f"# VWAP fade parameter search on {sym} ({micro})\n",
         f"{len(combos)} configs; {len(valid)} with at least 300 exploration trades. Explore 2008 to {EXPL_END - 1}, validate {EXPL_END} to {VAL_END - 1}, holdout {VAL_END} to 2026.\n",
         f"Luck baseline: {n_pos_ex} of {len(valid)} configs positive on exploration, {n_pos_va} of {len(valid)} positive on validation.\n",
         "## Top 10 by exploration net avgR\n", "| " + " | ".join(names) + " | n explore | avgR explore | n validate | avgR validate |", "|" + "---|" * (len(names) + 4)]
    for r in top:
        L.append("| " + " | ".join(str(x) for x in r["cfg"]) + f" | {r['n_ex']} | {r['m_ex']:+.4f} | {r['n_va']} | {r['m_va']:+.4f} |")
    L += [f"\n## Chosen (best validation among the top 10): {dict(zip(names, chosen['cfg']))}\n",
          f"**Holdout {VAL_END} to 2026: {len(ho)} trades, net avgR {m:+.4f}, t {t:.2f} -> {'PASS' if (ho and m > 0 and t > 2.0) else 'no'}**\n"]
    if chosen.get("hours") is not None: L.append(f"Entry hours kept (chosen on exploration): {chosen['hours']}\n")
    by_h = defaultdict(lambda: ([], []))
    for x in chosen["trades"]:
        y = int(x["session"][:4]); h = int(x["entry_time"][11:13])
        if y < EXPL_END: by_h[h][0].append(x["R"])
        elif y >= VAL_END: by_h[h][1].append(x["R"])
    L += ["By entry hour (ET), chosen config:\n", "| hour | explore n | explore avgR | holdout n | holdout avgR |", "|---|---|---|---|---|"]
    for h in sorted(by_h):
        e, o = by_h[h]
        L.append(f"| {h:02d} | {len(e)} | {np.mean(e) if e else float('nan'):+.4f} | {len(o)} | {np.mean(o) if o else float('nan'):+.4f} |")
    L.append("")
    if ho:
        for why in ("target", "stop", "time"):
            sub = [r for r in ho if r["why"] == why]
            if sub: L.append(f"- exits by {why}: {len(sub)} ({len(sub) / len(ho):.0%}), avgR {np.mean([r['R'] for r in sub]):+.3f}")
        yrs = defaultdict(list)
        for r in ho: yrs[r["session"][:4]].append(r["R"])
        L.append("- by year: " + ", ".join(f"{y}: {np.mean(v):+.3f} (n={len(v)})" for y, v in sorted(yrs.items())))
        with open(os.path.join(OUT, f"vwap_opt_{sym}_trades.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(ho[0].keys())); w.writeheader(); w.writerows(ho)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, f"vwap_opt_{sym}.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/vwap_opt_{sym}.md")


if __name__ == "__main__":
    main()
