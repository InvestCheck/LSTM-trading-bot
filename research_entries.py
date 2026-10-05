#!/usr/bin/env python3
"""Entry rules: explored on 2008 to 2016, tested on 2017 to 2026.

Reads research/intrabar/signals.csv (from research_exits.py). The exploration
half was examined by hand on 2026-10-05; the holdout had not been looked at
when the rule list below was written. Seven preregistered tests, one sided
Bonferroni on the quarter block bootstrap t.

Rules (all computable before the order is placed, so compatible with resting
orders at the line):
  small_stop      initial risk <= 2.5 ATR
  day_session     entry hour 8 to 16 ET inclusive
  no_equity_idx   exclude equity index futures
  shorts_only     support breaks only
  four_touches    line has >= 4 touches
  cheap_cost      instrument's average round trip cost <= 0.05R
  combined        small_stop AND day_session AND no_equity_idx AND cheap_cost

Tick units in instruments.py are 100x too small for GF, HE, LE, KE (the vendor
quotes them in cents); their net R is recomputed here with corrected ticks.

Usage (repo folder):  python3 research_entries.py
"""
import csv, os, statistics as st
from collections import defaultdict
from statistics import NormalDist
import numpy as np

SRC = "research/intrabar/signals.csv"
OUT = "research/entries_report.md"
SPLIT_YEAR = 2017
BOOT_REPS, SEED = 400, 11
TICK_FIX = {"GF": 0.025, "HE": 0.025, "LE": 0.025, "KE": 0.25}
EQUITY = set("ES NQ RTY EW NIY NKD YM FDAX FDXM FESX FXXP FCE FTI FTUK MFS MME".split())
COST_CAP = 0.05

RULES = {
    "small_stop":    lambda r: r["risk_atr"] <= 2.5,
    "day_session":   lambda r: 8 <= r["hour"] <= 16,
    "no_equity_idx": lambda r: r["symbol"] not in EQUITY,
    "shorts_only":   lambda r: r["dir"] < 0,
    "four_touches":  lambda r: r["touches"] >= 4,
    "cheap_cost":    lambda r: r["inst_cost"] <= COST_CAP,
}
RULES["combined"] = lambda r: (RULES["small_stop"](r) and RULES["day_session"](r)
                               and RULES["no_equity_idx"](r) and RULES["cheap_cost"](r))
N_TESTS = len(RULES)
Z = NormalDist().inv_cdf(1 - 0.05 / N_TESTS)


def load():
    rows = []
    for r in csv.DictReader(open(SRC)):
        if r["why_engine"] == "skipped": continue
        gross = float(r["gross_engine"]); net = float(r["R_engine"])
        rpx = abs(float(r["entry"]) - float(r["stop0"]))
        if r["symbol"] in TICK_FIX and rpx > 0:
            net = gross - 2.0 * TICK_FIX[r["symbol"]] / rpx
        rows.append(dict(symbol=r["symbol"], year=int(r["entry_time"][:4]), quarter=int(r["quarter"]),
                         dir=int(r["dir"]), touches=int(r["touches"]), hour=int(r["hour"]),
                         risk_atr=float(r["risk_atr"]), gross=gross, net=net, cost=gross - net))
    # instrument average cost (a property of tick and stop size, not of outcomes)
    by = defaultdict(list)
    for r in rows: by[r["symbol"]].append(r["cost"])
    avg = {s: float(np.mean(v)) for s, v in by.items()}
    for r in rows: r["inst_cost"] = avg[r["symbol"]]
    return rows, avg


def block_diff(rows, keep, reps=BOOT_REPS, seed=SEED):
    """avgR(in) - avgR(out), with its bootstrap std over calendar quarters."""
    by_q = defaultdict(list)
    for r in rows: by_q[r["quarter"]].append((r["net"], keep(r)))
    keys = list(by_q); rng = np.random.default_rng(seed); diffs = []
    for _ in range(reps):
        pick = rng.integers(0, len(keys), len(keys))
        a = [v for i in pick for v, k in by_q[keys[i]] if k]; b = [v for i in pick for v, k in by_q[keys[i]] if not k]
        if a and b: diffs.append(np.mean(a) - np.mean(b))
    inn = [r["net"] for r in rows if keep(r)]; out = [r["net"] for r in rows if not keep(r)]
    d = (np.mean(inn) if inn else 0) - (np.mean(out) if out else 0)
    sd = float(np.std(diffs)) if diffs else float("nan")
    return inn, out, d, (d / sd if sd and sd > 0 else float("nan"))


def block_t(vals, quarters, reps=BOOT_REPS, seed=SEED):
    by_q = defaultdict(list)
    for v, q in zip(vals, quarters): by_q[q].append(v)
    keys = list(by_q); rng = np.random.default_rng(seed); means = []
    arrs = [np.asarray(by_q[k]) for k in keys]
    for _ in range(reps):
        pick = rng.integers(0, len(arrs), len(arrs)); means.append(np.concatenate([arrs[i] for i in pick]).mean())
    sd = float(np.std(means)); m = float(np.mean(vals))
    return m, (m / sd if sd > 0 else float("nan"))


def fmt(v): return f"{np.mean(v):+.4f}" if len(v) else "n/a"


def main():
    rows, avg_cost = load()
    expl = [r for r in rows if r["year"] < SPLIT_YEAR]
    hold = [r for r in rows if r["year"] >= SPLIT_YEAR]
    yrs = (max(r["year"] for r in hold) - SPLIT_YEAR + 1)
    L = ["# Entry rules: explored 2008 to 2016, tested 2017 to 2026\n",
         f"Exploration {len(expl)} trades (avgR {np.mean([r['net'] for r in expl]):+.4f}), "
         f"holdout {len(hold)} trades (avgR {np.mean([r['net'] for r in hold]):+.4f}). "
         f"{N_TESTS} preregistered tests, one sided threshold on the block bootstrap t: **{Z:.2f}**. "
         f"Costs 2 ticks per round trip (GF, HE, LE, KE ticks corrected).\n",
         f"Cheap instruments (avg cost <= {COST_CAP}R): " +
         " ".join(sorted(s for s, c in avg_cost.items() if c <= COST_CAP)) + "\n",
         "| rule | exploration in / out | holdout in: n, avgR, win% | holdout out: n, avgR | diff | boot t | verdict |",
         "|---|---|---|---|---|---|---|"]
    for name, keep in RULES.items():
        ei = [r["net"] for r in expl if keep(r)]; eo = [r["net"] for r in expl if not keep(r)]
        inn, out, d, t = block_diff(hold, keep)
        win = np.mean(np.asarray(inn) > 0.01) * 100 if inn else 0
        share = len(inn) / max(1, len(hold))
        verdict = "PASS" if (t > Z and share >= 0.2) else ("too few kept" if t > Z else "no")
        L.append(f"| {name} | {fmt(ei)} / {fmt(eo)} | {len(inn)}, {fmt(inn)}, {win:.0f}% | {len(out)}, {fmt(out)} | "
                 f"{d:+.4f} | {t:.2f} | {verdict} |")
    # what the combined rule would be worth, holdout only
    comb = [r for r in hold if RULES["combined"](r)]
    m, t = block_t([r["net"] for r in comb], [r["quarter"] for r in comb])
    L.append(f"\n**Combined rule on the holdout:** {len(comb)} trades over {yrs} years "
             f"({len(comb) / yrs:.0f} per year), net avgR {m:+.4f}, pooled t {t:.2f}, "
             f"total {sum(r['net'] for r in comb):+.0f}R ({sum(r['net'] for r in comb) / yrs:+.0f}R per year).")
    base = [r["net"] for r in hold]
    L.append(f"Unfiltered holdout for comparison: {len(hold)} trades, net avgR {np.mean(base):+.4f}, "
             f"{sum(base) / yrs:+.0f}R per year.\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
