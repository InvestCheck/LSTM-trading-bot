#!/usr/bin/env python3
"""How big is one tick relative to the stop distance?

If the R distance on a contract is only a few ticks, a 1-tick round-trip
slippage charge is a large fraction of the whole bet and the costed result says
more about the cost model than about the strategy. Run this over the trade
files before trusting any per-instrument number.

  python3 tick_sanity.py            # every backtests/trades_*.csv, worst first
  python3 tick_sanity.py ZQ SR3 ER  # named symbols only
  python3 tick_sanity.py --portfolio  # aggregate R at several exclusion thresholds

The --portfolio view exists so the exclusion threshold is not chosen to flatter
the headline. It reports the total at every cutoff, so the reader can see how
sensitive the number is to where the line is drawn.
"""
import csv, glob, os, statistics, sys
from instruments import TICKS

args = [a for a in sys.argv[1:] if not a.startswith("--")]
portfolio = "--portfolio" in sys.argv

rows = []
syms = args or sorted(os.path.basename(p)[7:-4]
                              for p in glob.glob("backtests/trades_*.csv"))
for s in syms:
    p = f"backtests/trades_{s}.csv"
    if not os.path.exists(p):
        continue
    tick = TICKS.get(s)
    recs = list(csv.DictReader(open(p)))
    rpx = [float(r["R_px"]) for r in recs if float(r["R_px"]) > 0]
    if not rpx or not tick:
        continue
    med = statistics.median(rpx)
    totR = sum(float(r["R_realized"]) for r in recs)
    rows.append((med / tick, s, len(rpx), tick, med, totR, len(recs)))

rows.sort()
hdr = f"{'symbol':8s} {'trades':>7s} {'tick':>10s} {'median R_px':>12s} {'R in ticks':>11s}  cost as % of R"
print(hdr); print("-" * len(hdr))
for ratio, s, n, tick, med, totR, ntr in rows:
    flag = "  <-- 1 tick swamps the bet" if ratio < 10 else ""
    print(f"{s:8s} {n:7d} {tick:10g} {med:12.5f} {ratio:11.1f}  {2/ratio:13.1%}{flag}")
print("-" * len(hdr))
print("'cost as % of R' is a 1-tick round trip against the median stop distance.")

if portfolio:
    print()
    hdr2 = (f"{'min ticks':>10s} {'kept':>6s} {'dropped':>8s} {'trades':>8s} "
            f"{'totalR':>10s} {'avgR':>8s}")
    print(hdr2); print("-" * len(hdr2))
    for cut in (0, 2, 4, 6, 8, 10, 15, 20):
        keep = [r for r in rows if r[0] >= cut]
        tr = sum(r[6] for r in keep)
        R = sum(r[5] for r in keep)
        print(f"{cut:10d} {len(keep):6d} {len(rows)-len(keep):8d} {tr:8d} "
              f"{R:+10.1f} {R/tr if tr else 0:+8.3f}")
    print("-" * len(hdr2))
    print("A stop narrower than the round-trip cost cannot be executed as designed.\n"
          "That is a mechanical exclusion criterion, not a performance one, and it\n"
          "has to be stated before reading the totals it produces.")
