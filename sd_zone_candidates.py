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
    setups = list(csv.DictReader(open(args[1]))); out = []; counts = {0: 0, 1: 0, 2: 0}; top = []; skipped = 0
    for s in setups:
        t = parse_time(s["date"], s["entry_time"]); d = 1 if s["dir"] == "Long" else -1 if s["dir"] == "Short" else 0
        if t is None or d == 0: skipped += 1; continue
        t_end = int(t.timestamp()) // 300 * 300                           # rejection bar end = entry floored to 5m
        j = int(np.searchsorted(T, t_end))
        if j >= n or T[j] != t_end: skipped += 1; continue                 # outside the data
        lo_a, hi_a = AGE.get(s["zone_age"], AGE[""]); a = A[j - 1]
        cands = []
        for k in range(max(6, j - hi_a - SLACK), j - max(0, lo_a - SLACK) + 1):
            if k >= j - 1 or rng[k] < 0.5: continue                        # at least one bar between the candle and the rejection
            if d > 0:
                if not (C[k] < O[k] and L[j] <= H[k] < C[j]): continue
                if C[k + 1:j].min() < L[k] or fmaxC[k] <= H[k]: continue
                spike = (fmaxC[k] - C[k]) / rng[k]; cont = int(C[k + 1] >= O[k + 1]); taps = taps_after_leaving(L[k + 1:j] > H[k], L[k + 1:j] <= H[k])
            else:
                if not (C[k] > O[k] and H[j] >= L[k] > C[j]): continue
                if C[k + 1:j].max() > H[k] or fminC[k] >= L[k]: continue
                spike = (C[k] - fminC[k]) / rng[k]; cont = int(C[k + 1] <= O[k + 1]); taps = taps_after_leaving(H[k + 1:j] < L[k], H[k + 1:j] >= L[k])
            age = j - k; in_bucket = int(lo_a <= age <= hi_a)
            cands.append(dict(k=k, in_bucket=in_bucket, spike=spike, cont=cont, taps=taps, age=age, cons_atr=span6[k] / A[k] if A[k] > 0 else np.nan,
                              appr_max=rmax6[j] / a, appr_net=abs(C[j - 1] - C[max(0, j - 13)]) / a))
        cands.sort(key=lambda c: (-c["in_bucket"], -c["spike"]))
        counts[min(len(cands), 2)] += 1
        for r, c in enumerate(cands[:TOPN]):
            k = c["k"]
            out.append(dict(notion_id=s["notion_id"], date=s["date"], entry_time=s["entry_time"], dir=s["dir"], result=s["result"], r=s["r"], approach=s["approach"],
                            with_trend=s["with_trend"], zone_age=s["zone_age"], rejection_bar_end=datetime.fromtimestamp(t_end, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                            rank=r + 1, pick="", zone_bar_start=datetime.fromtimestamp(int(T[k]) - 300, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                            zone_high=f"{H[k]:.2f}", zone_low=f"{L[k]:.2f}", in_bucket=c["in_bucket"], spike_mult=f"{c['spike']:.2f}", cons_atr=f"{c['cons_atr']:.2f}",
                            next_cont=c["cont"], taps=c["taps"], age_bars=c["age"], appr_max_atr=f"{c['appr_max']:.2f}", appr_net_atr=f"{c['appr_net']:.2f}"))
            if r == 0: top.append(dict(c, setup=s))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sd_zone_candidates.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(f"{len(setups)} setups, {skipped} skipped (no time, no direction or outside the data); candidates: none {counts[0]}, one {counts[1]}, two or more {counts[2]}")
    if top:
        print(f"\nTop candidate, share passing each engine rule element ({len(top)} setups):")
        for name, fn in [("spike >= 2x", lambda c: c["spike"] >= 2), ("spike >= 3x", lambda c: c["spike"] >= 3), ("consolidation <= 2 ATR", lambda c: c["cons_atr"] <= 2),
                         ("consolidation <= 3 ATR", lambda c: c["cons_atr"] <= 3), ("next bar continues", lambda c: c["cont"] == 1), ("fresh (no taps)", lambda c: c["taps"] == 0),
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
