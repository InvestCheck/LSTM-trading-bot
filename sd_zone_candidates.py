#!/usr/bin/env python3
"""Reconstruct the zones behind Adam's logged NQ supply and demand setups from the
bars, using what the log already holds: entry time (the rejection bar is the 5m bar
that closed just before it) and zone age (5m bars back from the rejection bar).

For each setup, candidate zone candles are the bars inside the age window that
  - are the opposite colour to the trade (bearish for a long)
  - were touched by the rejection bar, which closed back outside them
    (long: rejection low <= candle high < rejection close)
  - were not closed through between the candle and the rejection (zone still live)
  - were left by price afterwards (some later close beyond the candle's far side)
Candidates are ranked: age window first, then the biggest spike after the candle.
If the strict geometry finds nothing, a ladder of relaxations is tried one at a time
(entry one or two bars after the rejection close, a touch within 0.3 ATR of the zone,
any colour zone candle, a 2 or 3 bar zone) and the report says which one worked, so
the geometry of Adam's zones can be read off the counts.
Nothing else from the engine's rule is imposed; instead every engine rule element is
scored on each candidate so we can see which elements Adam's zones fail:
  spike_mult   (max close within 6 bars - close) / candle range
  cons_atr     span of the 6 bars ending at the candle / ATR
  next_cont    the next bar continues (bullish after a bearish zone candle)
  taps         bars that traded back into the zone after price first cleared it, before
               the rejection (0 = fresh)
  age          bars from the candle to the rejection bar
  approach     max bar range over the 6 bars into the rejection / ATR, and the net
               move over the 12 bars before the rejection / ATR (approach speed)

Outputs research/sd_zone_candidates.csv (top 5 per setup, with a blank `pick` column
for confirmation) and prints: setups with 0 / 1 / 2+ candidates, and for the top
candidate the share passing each engine rule element and each full rule set.

Usage (repo folder):  python3 sd_zone_candidates.py DATA_DIR_1m research/sd_log_setups.csv [--symbol NQ]
"""
import os, sys, csv, glob, re
from datetime import datetime, timedelta, timezone
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

from research_sd import load_1m, resample, atr

OUT = "research"
AGE = {"0-10": (0, 10), "10-30": (10, 30), "30-75": (30, 75), "75-150": (75, 150), "150-300": (150, 300), "300-450": (300, 450),
       "450-600": (450, 600), "600-750": (600, 750), "750+": (750, 1500), "": (0, 600)}
SLACK = 5                      # bars of tolerance on each side of the age bucket
TOPN = 5


def parse_time(d, s):
    s = s.strip().replace(" ", "")
    if not s: return None
    m = re.match(r"^(\d{1,2}):?(\d{2})?", s)
    if not m: return None
    h = int(m.group(1)); mi = int(m.group(2) or 0)
    if h > 23: return None
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=h, minutes=mi)


def taps_after_leaving(left, touched):
    """Bars that traded into the zone after price first cleared it (bars before that are the spike itself)."""
    idx = np.flatnonzero(left)
    return int(touched[idx[0] + 1:].sum()) if len(idx) else 0


LADDER = [("strict", 0, 0.0, False, 1), ("entry 1 bar later", 1, 0.0, False, 1), ("entry 2 bars later", 2, 0.0, False, 1),
          ("touch within 0.3 ATR", 0, 0.3, False, 1), ("any colour candle", 0, 0.0, True, 1), ("2 bar zone", 0, 0.0, True, 2), ("3 bar zone", 0, 0.0, True, 3),
          ("2 bar zone, touch 0.3 ATR, entry up to 2 bars later", 2, 0.3, True, 2)]


def find(j, d, lo_a, hi_a, tol, anycol, width, T, O, H, L, C, A, rng, fmaxC, fminC, span6, rmax6):
    """Candidate zone candles for a rejection bar j. width > 1 merges the `width` bars ending at k into one zone."""
    out = []; a = A[j - 1] if A[j - 1] > 0 else 1e-9
    for k in range(max(6, j - hi_a - SLACK), j - max(0, lo_a - SLACK) + 1):
        if k >= j - 1: continue
        k0 = k - width + 1
        zh, zl = H[k0:k + 1].max(), L[k0:k + 1].min()
        if zh - zl < 0.5: continue
        if d > 0:
            if not anycol and not C[k] < O[k]: continue
            if not (L[j] <= zh + tol * a and zh < C[j]): continue
            if C[k + 1:j].min() < zl or fmaxC[k] <= zh: continue
            spike = (fmaxC[k] - C[k]) / (zh - zl); cont = int(C[k + 1] >= O[k + 1]); taps = taps_after_leaving(L[k + 1:j] > zh, L[k + 1:j] <= zh)
            closes_in = int(((C[k + 1:j] <= zh) & (C[k + 1:j] >= zl)).sum())
        else:
            if not anycol and not C[k] > O[k]: continue
            if not (H[j] >= zl - tol * a and zl > C[j]): continue
            if C[k + 1:j].max() > zh or fminC[k] >= zl: continue
            spike = (C[k] - fminC[k]) / (zh - zl); cont = int(C[k + 1] <= O[k + 1]); taps = taps_after_leaving(H[k + 1:j] < zl, H[k + 1:j] >= zl)
            closes_in = int(((C[k + 1:j] <= zh) & (C[k + 1:j] >= zl)).sum())
        age = j - k
        out.append(dict(k=k, zh=zh, zl=zl, in_bucket=int(lo_a <= age <= hi_a), spike=spike, cont=cont, taps=taps, closes_in=closes_in, age=age,
                        cons_atr=span6[k0] / A[k0] if A[k0] > 0 else np.nan, appr_max=rmax6[j] / a, appr_net=abs(C[j - 1] - C[max(0, j - 13)]) / a))
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 2: sys.exit(__doc__)
    sym = args[args.index("--symbol") + 1] if "--symbol" in args else "NQ"
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    T, O, H, L, C, V = resample(*load_1m(cat[sym]), 5); n = len(T); A = atr(H, L, C); rng = H - L
    fmaxC = np.full(n, -np.inf); fminC = np.full(n, np.inf)
    fmaxC[:n - 6] = swv(C[1:], 6).max(axis=1); fminC[:n - 6] = swv(C[1:], 6).min(axis=1)
    span6 = np.full(n, np.nan); span6[5:] = swv(H, 6).max(axis=1) - swv(L, 6).min(axis=1)
    rmax6 = np.full(n, np.nan); rmax6[5:] = swv(rng, 6).max(axis=1)
    setups = list(csv.DictReader(open(args[1]))); out = []; counts = {0: 0, 1: 0, 2: 0}; top = []; skipped = 0; relaxed = {}; missing = []
    for s in setups:
        t = parse_time(s["date"], s["entry_time"]); d = 1 if s["dir"] == "Long" else -1 if s["dir"] == "Short" else 0
        if t is None or d == 0: skipped += 1; continue
        t_end = int(t.timestamp()) // 300 * 300                           # rejection bar end = entry floored to 5m
        j = int(np.searchsorted(T, t_end))
        if j >= n or T[j] != t_end: skipped += 1; continue                 # outside the data
        lo_a, hi_a = AGE.get(s["zone_age"], AGE[""])
        cands, relax = [], ""
        for name, off, tol, anycol, width in LADDER:                       # strict geometry first, then one relaxation at a time
            jj = j - off
            if jj < 10 or jj >= n: continue
            cands = find(jj, d, lo_a, hi_a, tol, anycol, width, T, O, H, L, C, A, rng, fmaxC, fminC, span6, rmax6)
            if cands: relax = name; break
        a = A[j - 1]
        cands.sort(key=lambda c: (-c["in_bucket"], -c["spike"]))
        counts[min(len(cands), 2)] += 1; relaxed[relax or "none"] = relaxed.get(relax or "none", 0) + 1
        if not cands:
            missing.append(f"  {s['date']} {s['entry_time']:>5s} {s['dir']:5s} age {s['zone_age'] or '?':8s} rejection bar O {O[j]:.2f} H {H[j]:.2f} L {L[j]:.2f} C {C[j]:.2f}  {s['result']} {s['r']}")
        for r, c in enumerate(cands[:TOPN]):
            k = c["k"]
            out.append(dict(notion_id=s["notion_id"], date=s["date"], entry_time=s["entry_time"], dir=s["dir"], result=s["result"], r=s["r"], approach=s["approach"],
                            with_trend=s["with_trend"], zone_age=s["zone_age"], rejection_bar_end=datetime.fromtimestamp(t_end, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                            rank=r + 1, pick="", geometry=relax, zone_bar_start=datetime.fromtimestamp(int(T[k]) - 300, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                            zone_high=f"{c['zh']:.2f}", zone_low=f"{c['zl']:.2f}", in_bucket=c["in_bucket"], spike_mult=f"{c['spike']:.2f}", cons_atr=f"{c['cons_atr']:.2f}",
                            next_cont=c["cont"], taps=c["taps"], closes_inside=c["closes_in"], age_bars=c["age"], appr_max_atr=f"{c['appr_max']:.2f}", appr_net_atr=f"{c['appr_net']:.2f}"))
            if r == 0: top.append(dict(c, setup=s))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sd_zone_candidates.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(f"{len(setups)} setups, {skipped} skipped (no time, no direction or outside the data); candidates: none {counts[0]}, one {counts[1]}, two or more {counts[2]}")
    print("Geometry that first produced a candidate: " + ", ".join(f"{k} {v}" for k, v in relaxed.items()))
    if missing: print("No candidate under any geometry:\n" + "\n".join(missing))
    if top:
        print(f"\nTop candidate, share passing each engine rule element ({len(top)} setups):")
        for name, fn in [("spike >= 2x", lambda c: c["spike"] >= 2), ("spike >= 3x", lambda c: c["spike"] >= 3), ("consolidation <= 2 ATR", lambda c: c["cons_atr"] <= 2),
                         ("consolidation <= 3 ATR", lambda c: c["cons_atr"] <= 3), ("next bar continues", lambda c: c["cont"] == 1), ("fresh (no taps)", lambda c: c["taps"] == 0), ("fresh (no close inside)", lambda c: c["closes_in"] == 0),
                         ("approach max bar <= 1.5 ATR", lambda c: c["appr_max"] <= 1.5), ("approach max bar <= 2.5 ATR", lambda c: c["appr_max"] <= 2.5),
                         ("age <= 2 sessions", lambda c: c["age"] <= 552)]:
            print(f"  {name:30s} {np.mean([fn(c) for c in top]) * 100:5.1f}%")
        full = lambda c: c["spike"] >= 2 and c["cons_atr"] <= 2 and c["cont"] == 1 and c["appr_max"] <= 1.5
        loose = lambda c: c["spike"] >= 2 and c["cons_atr"] <= 3 and c["appr_max"] <= 2.5
        print(f"  {'engine stated rule (all of spike 2x, cons 2, cont, approach 1.5)':62s} {np.mean([full(c) for c in top]) * 100:5.1f}%")
        print(f"  {'loosest grid rule (spike 2x, cons 3, approach 2.5)':62s} {np.mean([loose(c) for c in top]) * 100:5.1f}%")
        for lab in ("Crash/Pump", "Slow selloff/Pump", "Consolidation", "Break and Retest"):
            sub = [c for c in top if c["setup"]["approach"] == lab]
            if sub: print(f"  approach label {lab:18s} n={len(sub):3d}  median net move 12 bars {np.median([c['appr_net'] for c in sub]):.2f} ATR, median max bar {np.median([c['appr_max'] for c in sub]):.2f} ATR")
    print(f"\n-> {OUT}/sd_zone_candidates.csv (confirm with the pick column or the Zone candle time field in Notion)")


if __name__ == "__main__":
    main()
