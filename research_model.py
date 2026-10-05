#!/usr/bin/env python3
"""Tier model for entries: what do the good signals have in common, tested honestly.

Fits a ridge regression of net R on features known BEFORE the order is placed
(previous bar measures, line geometry, stop size, time, instrument cost and
class), using only 2008 to 2016 trades. Then ranks the 2017 to 2026 trades by
the model's prediction. One preregistered test: avgR of the top half by score
minus avgR of the bottom half, on the holdout, block bootstrap over quarters,
one sided 5% (z 1.64). Deciles are reported for reading, not for deciding.

Nothing from the holdout touches the fit. Features measured at the entry bar's
close (d_e21, room, mom5, ...) are deliberately excluded: they are not known
when a resting order goes in.

Reads research/intrabar/signals.csv (regenerate it first with the updated
research_exits.py so the p_* columns exist). Writes research/model_report.md.

Usage (repo folder):  python3 research_model.py
"""
import csv, os, math
from collections import defaultdict
from statistics import NormalDist
import numpy as np

SRC = "research/intrabar/signals.csv"
OUT = "research/model_report.md"
SPLIT_YEAR = 2017
BOOT_REPS, SEED = 400, 13
RIDGE = 10.0
TICK_FIX = {"GF": 0.025, "HE": 0.025, "LE": 0.025, "KE": 0.25}
CLASSES = {
    "FX": "A6 AD B6 CNH E1 E6 E7 J1 J7 MP N6 NOK SEK RP RY SIR DX".split(),
    "EQ": "ES NQ RTY EW NIY NKD YM FDAX FDXM FESX FXXP FCE FTI FTUK MFS MME".split(),
    "RATES": "ZT ZF ZN TN UB FGBL FGBM FGBX FOAT FBTP FBON G".split(),
    "ENERGY": "CL BZ B HO RB NG".split(),
    "METALS": "GC MGC SI HG PA PL".split(),
    "AGS": "ZC XC ZS ZL ZM KE CT SB RS DC GF HE LE".split(),
}
PRE_ORDER = ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20", "p_ext_1y", "p_atr_ratio", "p_risk_atr"]
Z = NormalDist().inv_cdf(0.95)


def load():
    rows = []
    for r in csv.DictReader(open(SRC)):
        if r["why_engine"] == "skipped": continue
        if "p_room" not in r: raise SystemExit("signals.csv has no p_* columns: rerun research_exits.py first")
        gross = float(r["gross_engine"]); net = float(r["R_engine"])
        rpx = abs(float(r["entry"]) - float(r["stop0"]))
        if r["symbol"] in TICK_FIX and rpx > 0: net = gross - 2.0 * TICK_FIX[r["symbol"]] / rpx
        rows.append(dict(symbol=r["symbol"], year=int(r["entry_time"][:4]), quarter=int(r["quarter"]), net=net,
                         cost=gross - net, dir=int(r["dir"]), touches=int(r["touches"]), span=int(r["span"]),
                         hour=int(r["hour"]), dow=int(r["dow"]), kind=r["kind"], stop_src=r["stop_src"],
                         **{k: float(r[k]) for k in PRE_ORDER}))
    by = defaultdict(list)
    for r in rows: by[r["symbol"]].append(r["cost"])
    avg = {s: float(np.mean(v)) for s, v in by.items()}
    for r in rows: r["inst_cost"] = avg[r["symbol"]]
    return rows


def featurize(r):
    cls = next((c for c, lst in CLASSES.items() if r["symbol"] in lst), "OTHER")
    x = [r[k] for k in PRE_ORDER]
    x += [math.log(r["span"]), r["touches"], 1.0 if r["dir"] > 0 else 0.0, 1.0 if r["stop_src"] == "ema" else 0.0,
          math.sin(2 * math.pi * r["hour"] / 24), math.cos(2 * math.pi * r["hour"] / 24),
          1.0 if r["dow"] == 6 else 0.0, r["inst_cost"]]
    x += [1.0 if cls == c else 0.0 for c in CLASSES]
    return x


NAMES = PRE_ORDER + ["log_span", "touches", "is_long", "stop_ema", "hour_sin", "hour_cos", "sunday", "inst_cost"] + list(CLASSES)


def block_diff(vals, keep, quarters, reps=BOOT_REPS, seed=SEED):
    by_q = defaultdict(list)
    for v, k, q in zip(vals, keep, quarters): by_q[q].append((v, k))
    keys = list(by_q); rng = np.random.default_rng(seed); diffs = []
    for _ in range(reps):
        pick = rng.integers(0, len(keys), len(keys))
        a = [v for i in pick for v, k in by_q[keys[i]] if k]; b = [v for i in pick for v, k in by_q[keys[i]] if not k]
        if a and b: diffs.append(np.mean(a) - np.mean(b))
    d = np.mean(vals[keep]) - np.mean(vals[~keep]); sd = float(np.std(diffs))
    return d, (d / sd if sd > 0 else float("nan"))


def main():
    rows = load()
    expl = [r for r in rows if r["year"] < SPLIT_YEAR]; hold = [r for r in rows if r["year"] >= SPLIT_YEAR]
    Xe = np.array([featurize(r) for r in expl]); ye = np.array([r["net"] for r in expl])
    Xh = np.array([featurize(r) for r in hold]); yh = np.array([r["net"] for r in hold])
    mu, sd = Xe.mean(0), Xe.std(0) + 1e-9
    Ze = (Xe - mu) / sd; Zh = (Xh - mu) / sd
    Ze1 = np.hstack([Ze, np.ones((len(Ze), 1))]); Zh1 = np.hstack([Zh, np.ones((len(Zh), 1))])
    reg = RIDGE * np.eye(Ze1.shape[1]); reg[-1, -1] = 0
    w = np.linalg.solve(Ze1.T @ Ze1 + reg, Ze1.T @ ye)
    pe, ph = Ze1 @ w, Zh1 @ w
    cut = float(np.median(pe))                       # threshold chosen on the exploration half
    keep = ph >= cut
    d, t = block_diff(yh, keep, np.array([r["quarter"] for r in hold]))
    verdict = "PASS" if t > Z else "no"

    L = ["# Tier model: pre order features, fit 2008 to 2016, ranked 2017 to 2026\n",
         f"Fit on {len(expl)} trades, tested on {len(hold)}. Ridge {RIDGE}. Threshold = exploration median score "
         f"({cut:+.4f}). One preregistered test, one sided z {Z:.2f}.\n",
         f"**Holdout, top half by score vs bottom half:** {keep.sum()} trades at {np.mean(yh[keep]):+.4f} vs "
         f"{(~keep).sum()} at {np.mean(yh[~keep]):+.4f}, diff {d:+.4f}, boot t {t:.2f} -> **{verdict}**\n",
         "| holdout decile by score | n | avgR | win% |", "|---|---|---|---|"]
    edges = np.quantile(ph, np.linspace(0, 1, 11))
    for i in range(10):
        m = (ph >= edges[i]) & (ph <= edges[i + 1]) if i == 9 else (ph >= edges[i]) & (ph < edges[i + 1])
        L.append(f"| {i + 1} ({'low' if i == 0 else 'high' if i == 9 else ''}) | {m.sum()} | {np.mean(yh[m]):+.4f} | {np.mean(yh[m] > 0.01) * 100:.0f}% |")
    L.append("\n| feature | weight (per std) |"); L.append("|---|---|")
    for n, ww in sorted(zip(NAMES, w[:-1]), key=lambda x: -abs(x[1])):
        L.append(f"| {n} | {ww:+.4f} |")
    L.append("\nWeights are the exploration fit; a weight only means something if the holdout test above passed.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
