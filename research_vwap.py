#!/usr/bin/env python3
"""VWAP standard deviation band fades on intraday futures data, on 1, 5 and 15
minute bars (the 5 and 15 minute bars are built from the 1 minute file,
aligned to the 18:00 ET session open).

Session VWAP is anchored at the 18:00 ET open; bands are +/- k volume weighted
standard deviations of typical price around it, cumulative within the session.
Every level used for a decision on bar i is the value at the close of bar i-1,
so nothing on the bar being traded is used to place its orders.

Two preregistered families, each tested once on the holdout at the timeframe
that did best on the exploration half (chosen by net avgR per trade):

  A  band3_limit   limit at the +3 band (short) / -3 band (long), filled when
                   touched; stop at the 4.5 band (1R = 1.5 bands); target VWAP;
                   a side re arms once a bar closes back inside the 2 band
  B  band2_reject  short when a bar pokes above the +2 band and closes back
                   below it with the close in the lower half of its range
                   (mirror for longs); entry at the next bar's open; stop one
                   tick beyond the rejection bar's extreme; target VWAP; a side
                   re arms once a bar closes back inside the 1 band

Common: flat at 16:45 ET; no entries in the first 60 minutes or the last 15;
band at least MIN_BAND_TICKS wide; one position at a time per instrument.
Conservative intrabar rule: if the entry bar's range also reaches the stop,
the trade is stopped on the entry bar; a target inside the entry bar does not
count. Costs: COMM per side per contract, one tick on stop and time exits.

Split: explore 2008 to 2016, test 2017 to 2026. Two holdout tests, PASS =
net avgR > 0 and monthly block bootstrap t > 2.0.

Usage (repo folder):  python3 research_vwap.py DATA_DIR_1m [--symbols ...]
Writes research/vwap_report.md and research/vwap_trades_<family>_<tf>m.csv
(each feeds prop_sim.py --trades).
"""
import os, sys, csv, math, glob, re
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from instruments import TICKS

OUT = "research"
SPLIT_YEAR = 2017
MIN_BAND_TICKS = 3
WARMUP_MIN = 60
FLAT_MIN_OF_DAY = 16 * 60 + 45          # 16:45 ET
LAST_ENTRY_MIN = FLAT_MIN_OF_DAY - 15
COMM = 1.5
BOOT_REPS, SEED = 400, 7
TIMEFRAMES = [1, 5, 15]
FAMILIES = {"band3_limit": dict(k_in=3.0, k_stop=4.5, rearm=2.0), "band2_reject": dict(k_in=2.0, rearm=1.0)}
MICROS = {                      # vendor symbol -> (micro, dollars per 1.0 of price)
    "ES": ("MES", 5), "NQ": ("MNQ", 2), "RTY": ("M2K", 5), "YM": ("MYM", 0.5), "GC": ("MGC", 10), "SI": ("SIL", 1000),
    "HG": ("MHG", 2500), "CL": ("MCL", 100), "NG": ("QG", 2500), "E6": ("M6E", 12500), "A6": ("M6A", 10000),
    "B6": ("M6B", 6250), "J1": ("MJY", 1250000), "E1": ("MSF", 12500),
}


def load_1m(path):
    ts, o, h, l, c, v = [], [], [], [], [], []
    day_cache = {}
    with open(path) as f:
        for line in f:
            p = line.split(",")
            if len(p) < 6: continue
            d = p[0][:10]
            base = day_cache.get(d)
            if base is None:
                base = int(datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), tzinfo=timezone.utc).timestamp()); day_cache[d] = base
            ts.append(base + int(p[0][11:13]) * 3600 + int(p[0][14:16]) * 60)
            o.append(float(p[1])); h.append(float(p[2])); l.append(float(p[3])); c.append(float(p[4])); v.append(float(p[5]))
    return np.array(ts, np.int64), np.array(o), np.array(h), np.array(l), np.array(c), np.array(v)


def resample(T, O, H, L, C, V, tf):
    """tf minute bars aligned to the 18:00 ET open. Labels stay bar END times."""
    if tf == 1: return T, O, H, L, C, V
    sess = (T - 60 + 6 * 3600) // 86400                 # session id: shift so 18:00 is the day boundary
    off = (T - 60 + 6 * 3600) % 86400                   # seconds since the session open, by bar start
    key = sess * 100000 + off // (tf * 60)
    change = np.concatenate([[True], key[1:] != key[:-1]])
    idx = np.flatnonzero(change)
    ends = np.concatenate([idx[1:], [len(T)]]) - 1
    return (T[ends], O[idx], np.maximum.reduceat(H, idx), np.minimum.reduceat(L, idx), C[ends], np.add.reduceat(V, idx))


def run_symbol(sym, bars, tf, family, cfg):
    tick = TICKS.get(sym, 0.0); micro, mult = MICROS[sym]
    T, O, H, L, C, V = bars; n = len(T); trades = []
    if tick <= 0 or n == 0: return trades
    sess = (T - 60 + 6 * 3600) // 86400
    mod = ((T // 60) % 1440).astype(int)               # minute of day of the bar's end label
    starts = np.concatenate([[0], np.flatnonzero(sess[1:] != sess[:-1]) + 1, [n]])
    for si in range(len(starts) - 1):
        a, b = starts[si], starts[si + 1]
        if (b - a) * tf < 120: continue
        tp = (H[a:b] + L[a:b] + C[a:b]) / 3.0; vol = np.maximum(V[a:b], 0.0)
        cv = np.cumsum(vol); cpv = np.cumsum(tp * vol); cpv2 = np.cumsum(tp * tp * vol)
        with np.errstate(invalid="ignore", divide="ignore"):
            vwap = cpv / cv; sd = np.sqrt(np.maximum(cpv2 / cv - vwap * vwap, 0.0))
        sdate = datetime.fromtimestamp(int(T[b - 1]), timezone.utc).strftime("%Y-%m-%d")
        pos = None; armed = {1: True, -1: True}; pending = None
        for j in range(1, b - a):
            i = a + j; m_day = mod[i]
            vw, s_ = vwap[j - 1], sd[j - 1]                      # levels known at the close of the previous bar
            if not np.isfinite(vw) or cv[j - 1] <= 0 or s_ <= 0: continue
            past_flat = m_day >= FLAT_MIN_OF_DAY or j == b - a - 1
            # ---- manage an open position
            if pos is not None:
                d, entry, stop, R, i0 = pos
                exit_px = why = None
                if (d < 0 and H[i] >= stop) or (d > 0 and L[i] <= stop):
                    gapped = (d < 0 and O[i] > stop) or (d > 0 and O[i] < stop)
                    exit_px = (O[i] if gapped else stop) - d * tick; why = "stop"
                elif (d < 0 and L[i] <= vw) or (d > 0 and H[i] >= vw):
                    exit_px = vw; why = "target"
                elif past_flat:
                    exit_px = C[i] - d * tick; why = "time"
                if exit_px is not None:
                    pnl_px = (exit_px - entry) * d
                    trades.append(dict(symbol=sym, micro=micro, tf=tf, family=family, session=sdate,
                                       entry_time=datetime.fromtimestamp(int(T[i0]), timezone.utc).strftime("%Y-%m-%d %H:%M"),
                                       dir=d, entry=entry, stop=stop, exit=exit_px, why=why, R_px=R,
                                       R=pnl_px / R - 2 * COMM / (R * mult), pnl_usd=pnl_px * mult - 2 * COMM, R_unit=R * mult,
                                       bars=j - (i0 - a)))
                    pos = None
                    continue
            # ---- pending rejection entry fills at this bar's open
            if pos is None and pending is not None and not past_flat:
                d, stop = pending; pending = None
                entry = O[i]; R = (stop - entry) if d < 0 else (entry - stop)
                if R > 0:
                    if (d < 0 and H[i] >= stop) or (d > 0 and L[i] <= stop):            # stopped on the entry bar
                        exit_px = stop - d * tick; pnl_px = (exit_px - entry) * d
                        trades.append(dict(symbol=sym, micro=micro, tf=tf, family=family, session=sdate,
                                           entry_time=datetime.fromtimestamp(int(T[i]), timezone.utc).strftime("%Y-%m-%d %H:%M"),
                                           dir=d, entry=entry, stop=stop, exit=exit_px, why="stop", R_px=R,
                                           R=pnl_px / R - 2 * COMM / (R * mult), pnl_usd=pnl_px * mult - 2 * COMM, R_unit=R * mult, bars=0))
                    else:
                        pos = (d, entry, stop, R, i)
                    continue
            # ---- re arm
            if C[i] < vw + cfg["rearm"] * s_: armed[-1] = True
            if C[i] > vw - cfg["rearm"] * s_: armed[1] = True
            if pos is not None or j * tf < WARMUP_MIN or m_day >= LAST_ENTRY_MIN or cfg["k_in"] * s_ < MIN_BAND_TICKS * tick:
                continue
            up, dn = vw + cfg["k_in"] * s_, vw - cfg["k_in"] * s_
            if family == "band3_limit":
                for d, lvl in ((-1, up), (1, dn)):
                    touched = (H[i] >= lvl and O[i] < lvl) if d < 0 else (L[i] <= lvl and O[i] > lvl)
                    if not armed[d] or not touched: continue
                    stop = vw + cfg["k_stop"] * s_ if d < 0 else vw - cfg["k_stop"] * s_
                    entry = lvl; R = abs(stop - entry); armed[d] = False
                    if (d < 0 and H[i] >= stop) or (d > 0 and L[i] <= stop):            # entry bar also reached the stop
                        exit_px = stop - d * tick; pnl_px = (exit_px - entry) * d
                        trades.append(dict(symbol=sym, micro=micro, tf=tf, family=family, session=sdate,
                                           entry_time=datetime.fromtimestamp(int(T[i]), timezone.utc).strftime("%Y-%m-%d %H:%M"),
                                           dir=d, entry=entry, stop=stop, exit=exit_px, why="stop", R_px=R,
                                           R=pnl_px / R - 2 * COMM / (R * mult), pnl_usd=pnl_px * mult - 2 * COMM, R_unit=R * mult, bars=0))
                    else:
                        pos = (d, entry, stop, R, i)
                    break
            else:   # band2_reject: rejection bar, enter next open
                rng_ = H[i] - L[i]
                if rng_ <= 0: continue
                if armed[-1] and H[i] >= up and C[i] < up and (C[i] - L[i]) <= 0.5 * rng_:
                    pending = (-1, H[i] + tick); armed[-1] = False
                elif armed[1] and L[i] <= dn and C[i] > dn and (H[i] - C[i]) <= 0.5 * rng_:
                    pending = (1, L[i] - tick); armed[1] = False
    return trades


def block_t(rows, key="R"):
    by = defaultdict(list)
    for r in rows: by[r["session"][:7]].append(r[key])
    keys = list(by); rng = np.random.default_rng(SEED); means = []
    for _ in range(BOOT_REPS):
        pick = rng.integers(0, len(keys), len(keys)); means.append(np.mean([v for i in pick for v in by[keys[i]]]))
    m = np.mean([r[key] for r in rows]); sd = float(np.std(means))
    return m, (m / sd if sd > 0 else float("nan"))


def summarize(rows, label):
    if not rows: return f"| {label} | 0 | | | | | | |"
    R = np.array([r["R"] for r in rows]); m, t = block_t(rows)
    days = len(set(r["session"] for r in rows)); daily = defaultdict(float)
    for r in rows: daily[r["session"]] += r["pnl_usd"]
    dv = np.array(list(daily.values()))
    pf = R[R > 0].sum() / max(1e-9, -R[R < 0].sum())
    return (f"| {label} | {len(R)} | {len(R) / max(1, days):.2f} | {m:+.4f} | {t:.2f} | {np.mean(R > 0) * 100:.0f}% | {pf:.2f} | "
            f"{dv.mean() / dv.std() * math.sqrt(252) if dv.std() > 0 else 0:.2f} |")


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 research_vwap.py DATA_DIR_1m [--symbols ...]")
    syms = list(MICROS)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    os.makedirs(OUT, exist_ok=True)
    results = {}                                   # (family, tf) -> trades
    for sym in syms:
        if sym not in cat: print(f"{sym}: no 1 minute file"); continue
        raw = load_1m(cat[sym])
        for tf in TIMEFRAMES:
            bars = resample(*raw, tf)
            for fam, cfg in FAMILIES.items():
                tr = run_symbol(sym, bars, tf, fam, cfg)
                results.setdefault((fam, tf), []).extend(tr)
                print(f"{sym:4s} {tf:2d}m {fam:13s} {len(tr):6d} trades, net avgR {np.mean([x['R'] for x in tr]) if tr else 0:+.4f}", flush=True)
    L = ["# VWAP band fades on 1, 5 and 15 minute bars (CME micro universe)\n",
         "Session VWAP anchored at 18:00 ET; all levels taken from the previous bar's close. Family A: limit fade at the 3 band, "
         "stop 4.5 band, target VWAP. Family B: rejection bar at the 2 band, next open entry, stop beyond the bar, target VWAP. "
         f"Flat 16:45 ET. Costs ${COMM} per side plus a tick on stop and time exits. Per family the timeframe with the best "
         "exploration net avgR is the one tested on the holdout; two tests, PASS = net avgR > 0 and monthly block bootstrap t > 2.0.\n"]
    verdicts = []
    for fam in FAMILIES:
        L += [f"\n## {fam}\n", "| set | trades | per session | net avgR | boot t | win% | PF | daily Sharpe (ann.) |", "|---|---|---|---|---|---|---|---|"]
        best_tf, best_m = None, -9
        for tf in TIMEFRAMES:
            allt = results.get((fam, tf), [])
            if allt:
                with open(os.path.join(OUT, f"vwap_trades_{fam}_{tf}m.csv"), "w", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(allt[0].keys())); w.writeheader(); w.writerows(allt)
            expl = [r for r in allt if int(r["session"][:4]) < SPLIT_YEAR]
            L.append(summarize(expl, f"{tf}m explore 2008-2016"))
            if expl and np.mean([r["R"] for r in expl]) > best_m: best_m, best_tf = np.mean([r["R"] for r in expl]), tf
        for tf in TIMEFRAMES:
            hold = [r for r in results.get((fam, tf), []) if int(r["session"][:4]) >= SPLIT_YEAR]
            tag = " (THE TEST)" if tf == best_tf else ""
            L.append(summarize(hold, f"{tf}m holdout 2017-2026{tag}"))
        hold = [r for r in results.get((fam, best_tf), []) if int(r["session"][:4]) >= SPLIT_YEAR] if best_tf else []
        if hold:
            m, t = block_t(hold); ok = m > 0 and t > 2.0
            verdicts.append(f"**{fam} at {best_tf}m: holdout net avgR {m:+.4f}, t {t:.2f} -> {'PASS' if ok else 'no'}**")
            L.append("\n" + verdicts[-1])
            for why in ("target", "stop", "time"):
                sub = [r for r in hold if r["why"] == why]
                if sub: L.append(f"- exits by {why}: {len(sub)} ({len(sub) / len(hold):.0%}), avgR {np.mean([r['R'] for r in sub]):+.3f}")
            L += ["\nPer instrument on the holdout at the tested timeframe:", "", "| instrument | trades | per session | net avgR | boot t | win% | PF | daily Sharpe |", "|---|---|---|---|---|---|---|---|"]
            for sym in syms:
                sub = [r for r in hold if r["symbol"] == sym]
                if sub: L.append(summarize(sub, sym))
    open(os.path.join(OUT, "vwap_report.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}/vwap_report.md and {OUT}/vwap_trades_<family>_<tf>m.csv")


if __name__ == "__main__":
    main()
