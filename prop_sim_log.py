#!/usr/bin/env python3
"""Prop firm plans run on Adam's own supply and demand log (the Notion NQ trade log),
not on a backtest.

The log is short (taken trades over about 15 weeks), so the plans are run on a day
block bootstrap: every weekday from 2017 to 2026 is assigned one randomly drawn log
day (with replacement, days with no trades included), keeping each day's trades
together. prop_sim.py then runs every plan on that synthetic stream exactly as it
does for the backtests. Sunday evening sessions in the log count as Monday.

R multiples in the log are before costs; commissions (COMM per side) are taken off
per contract. --shift subtracts a constant from every trade's R, to see how the
plans look if the logged edge is overstated (one standard error on 128 trades is
about 0.12R).

Usage (repo folder):
  python3 prop_sim_log.py research/sd_log_nq.csv [--r-unit 40] [--shift 0] [--seed 0] [--plan NAME] [--no-consistency]
    --r-unit   dollars of risk per contract (MNQ: 2 x stop in points; 40 = a 20 point stop)
Writes research/prop_log_trades_<shift>.csv and research/prop_log_report_<shift>.md.
"""
import os, sys, csv, subprocess
from datetime import datetime, timedelta
import numpy as np

OUT = "research"; COMM = 1.5
START, END = datetime(2017, 1, 2).date(), datetime(2026, 12, 31).date()


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    r_unit = float(args[args.index("--r-unit") + 1]) if "--r-unit" in args else 40.0
    shift = float(args[args.index("--shift") + 1]) if "--shift" in args else 0.0
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 0
    by_day = {}
    for r in csv.DictReader(open(args[0])):
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        if d.weekday() == 6: d += timedelta(days=1)
        if d.weekday() == 5: d += timedelta(days=2)
        by_day.setdefault(d, []).extend(float(x) for x in r["rs"].split(","))
    d0, d1 = min(by_day), max(by_day); log_days = []
    d = d0
    while d <= d1:
        if d.weekday() < 5: log_days.append(by_day.get(d, []))
        d += timedelta(days=1)
    allr = np.array([x for v in log_days for x in v])
    print(f"log: {len(allr)} trades on {sum(1 for v in log_days if v)} of {len(log_days)} weekdays {d0} to {d1}, "
          f"avgR {allr.mean():+.3f} (sd {allr.std():.2f}, t {allr.mean() / (allr.std() / np.sqrt(len(allr))):.2f}), shift {shift:+.2f} -> avgR {allr.mean() + shift:+.3f}")
    rng = np.random.default_rng(seed); os.makedirs(OUT, exist_ok=True)
    tag = f"{shift:+.2f}".replace("+", "p").replace("-", "m")
    path = os.path.join(OUT, f"prop_log_trades_{tag}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["session", "symbol", "micro", "R_unit", "R", "pnl_usd"]); n = 0
        d = START
        while d <= END:
            if d.weekday() < 5:
                for R in log_days[rng.integers(len(log_days))]:
                    w.writerow([d.strftime("%Y-%m-%d"), "NQ", "MNQ", f"{r_unit:.2f}", f"{R + shift:.3f}", f"{(R + shift) * r_unit - 2 * COMM:.2f}"]); n += 1
            d += timedelta(days=1)
    print(f"{n} synthetic trades -> {path}")
    extra = [a for a in ("--no-consistency",) if a in args] + (["--plan", args[args.index("--plan") + 1]] if "--plan" in args else [])
    subprocess.run([sys.executable, "prop_sim.py", "--trades", path] + extra, check=True)
    rep = os.path.join(OUT, f"prop_log_report_{tag}.md"); os.replace(os.path.join(OUT, "prop_report.md"), rep)
    print(f"-> {rep}")


if __name__ == "__main__":
    main()
