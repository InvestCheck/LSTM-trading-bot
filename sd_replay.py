#!/usr/bin/env python3
"""Replay Adam's own logged S&D setups with mechanical management, to locate the edge.

Input: research/sd_zone_candidates.csv (rank 1 zone per setup, from sd_zone_candidates.py)
and research/sd_log_setups.csv (his exit time, his R, his labels). For each setup the
entry is the open of the bar after the rejection bar, a tick worse; the stop is the
zone's far wick plus max(3 ticks, 0.15 ATR); 1R = entry to stop. Variants:
  fixed_2R   fixed stop, target 2R            be_2R   stop to entry at +1R, target 2R
  fixed_3R   fixed stop, target 3R            be_3R   stop to entry at +1R, target 3R
  flat       fixed stop, target 3R, flat at 16:45 ET of the entry session
  his_exit   fixed stop, exit at the close of the bar holding his logged exit time
Stop before target when both are hit in a bar. Costs: a tick each way plus commissions.
The comparison is the mechanical R against his logged R on the same setups, overall
and by his labels (with trend, approach, taken or scratch).

Usage (repo folder):  python3 sd_replay.py DATA_DIR_1m [--symbol NQ]
Writes research/sd_replay.csv.
"""
import os, sys, csv, glob, re
from datetime import datetime, timedelta, timezone
import numpy as np

from research_sd import load_1m, resample, atr
from sd_zone_candidates import parse_time

OUT = "research"; COMM = 1.5; MULT = 2.0; TICK = 0.25; FLAT_MIN = 16 * 60 + 45; MAX_BARS = 2 * 276
VARIANTS = ["fixed_2R", "fixed_3R", "be_2R", "be_3R", "flat", "his_exit"]


def replay(j, d, zh, zl, T, O, H, L, C, A, mod, sess, exit_ts, TICK=TICK, MULT=MULT):
    n = len(T); i0 = j + 1
    if i0 >= n: return None
    entry = O[i0] + d * TICK; a = A[j]
    stop = (zl - max(3 * TICK, 0.15 * a)) if d > 0 else (zh + max(3 * TICK, 0.15 * a))
    R = (entry - stop) * d
    if R <= 0: return None
    cost = 2 * COMM / (R * MULT)
    res = {}
    for v in VARIANTS:
        tgt_r = 2 if v.endswith("2R") else 3 if v.endswith("3R") or v == "flat" else 1e9
        be = v.startswith("be"); s = stop; armed = False; out = None
        for k in range(i0, min(n, i0 + MAX_BARS)):
            if be and armed and ((d > 0 and L[k] <= entry) or (d < 0 and H[k] >= entry)):
                out = (min(O[k], entry) if d > 0 else max(O[k], entry)) - d * TICK; break
            if (d > 0 and L[k] <= s) or (d < 0 and H[k] >= s):
                out = ((O[k] if (d > 0 and O[k] < s) or (d < 0 and O[k] > s) else s)) - d * TICK; break
            tgt = entry + d * tgt_r * R
            if (d > 0 and H[k] >= tgt) or (d < 0 and L[k] <= tgt): out = tgt; break
            if not armed and ((d > 0 and H[k] >= entry + R) or (d < 0 and L[k] <= entry - R)): armed = True
            if v == "flat" and sess[k] == sess[i0] and (mod[k] >= FLAT_MIN or k == n - 1 or sess[k + 1] != sess[i0]): out = C[k] - d * TICK; break
            if v == "his_exit" and exit_ts is not None and T[k] >= exit_ts: out = C[k] - d * TICK; break
        if out is None: out = C[min(n - 1, i0 + MAX_BARS - 1)] - d * TICK
        res[v] = (out - entry) * d / R - cost
    res["R_px"] = R
    return res


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    sym = args[args.index("--symbol") + 1] if "--symbol" in args else "NQ"
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    T, O, H, L, C, V = resample(*load_1m(cat[sym]), 5); A = atr(H, L, C)
    mod = ((T // 60) % 1440).astype(int); sess = (T - 60 + 6 * 3600) // 86400
    setups = {s["notion_id"]: s for s in csv.DictReader(open(os.path.join(OUT, "sd_log_setups.csv")))}
    cands = [c for c in csv.DictReader(open(os.path.join(OUT, "sd_zone_candidates.csv"))) if c["rank"] == "1"]
    rows = []
    for c in cands:
        s = setups[c["notion_id"]]; d = 1 if c["dir"] == "Long" else -1
        t_end = int(datetime.strptime(c["rejection_bar_end"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        j = int(np.searchsorted(T, t_end))
        if j >= len(T) or T[j] != t_end: continue
        xt = parse_time(s["date"], s["exit_time"].split("(")[0]) if s["exit_time"] else None
        if xt is not None and xt.timestamp() <= t_end: xt += timedelta(days=1)
        r = replay(j, d, float(c["zone_high"]), float(c["zone_low"]), T, O, H, L, C, A, mod, sess, int(xt.timestamp()) if xt else None)
        if r is None: continue
        rows.append(dict(notion_id=c["notion_id"], date=s["date"], entry_time=s["entry_time"], dir=c["dir"], taken=int(s["result"] != "Scratch"), his_R=float(s["r"]) if s["r"] else np.nan,
                         with_trend=s["with_trend"], approach=s["approach"], fresh=s["fresh"], geometry=c["geometry"], R_px=round(r["R_px"], 2), **{v: round(r[v], 3) for v in VARIANTS}))
    with open(os.path.join(OUT, "sd_replay.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    def line(label, sub):
        if not sub: return
        his = [r["his_R"] for r in sub if not np.isnan(r["his_R"])]
        print(f"  {label:34s} n={len(sub):3d}  his R {np.mean(his) if his else float('nan'):+.2f}   " + "  ".join(f"{v} {np.mean([r[v] for r in sub]):+.2f}" for v in VARIANTS))
    print(f"{len(rows)} setups replayed (rank 1 zone). Mechanical R per trade vs his logged R, same setups:\n")
    taken = [r for r in rows if r["taken"]]; scratch = [r for r in rows if not r["taken"]]
    line("all setups", rows); line("taken", taken); line("not taken (his R is hindsight)", scratch)
    print()
    for v_ in ("Y", "N"): line(f"taken, with trend {v_}", [r for r in taken if r["with_trend"] == v_])
    for lab in ("Slow selloff/Pump", "Consolidation", "Crash/Pump", "Break and Retest"): line(f"taken, {lab}", [r for r in taken if r["approach"] == lab])
    line("taken, strict geometry", [r for r in taken if r["geometry"] == "strict"]); line("taken, entry 1 to 2 bars later", [r for r in taken if r["geometry"].startswith("entry")])
    his = np.array([r["his_R"] for r in taken]); mech = np.array([r["fixed_3R"] for r in taken])
    ok = ~np.isnan(his)
    if ok.sum() > 5: print(f"\ncorrelation of his R with mechanical fixed_3R R on taken setups: {np.corrcoef(his[ok], mech[ok])[0, 1]:+.2f}; "
                           f"stopped out mechanically (fixed_3R < -0.9): {np.mean(mech < -0.9) * 100:.0f}% vs his losses {np.mean(his[ok] <= -0.9) * 100:.0f}%")
    print(f"\n-> {OUT}/sd_replay.csv")


if __name__ == "__main__":
    main()
