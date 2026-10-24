#!/usr/bin/env python3
"""Three v3 studies, three preregistered tests, on the engine's trades.

A. Tier model refit with ADX, breadth and cluster breadth added to the frozen
   feature set (same ridge fit, same exploration years). Test: within the v2
   trades (cheap instruments, old score at or above the old cutoff) on the
   holdout, new score at or above its exploration v2 median vs below, avgR
   difference, quarter block bootstrap, one sided z 1.64. Reference rows: the
   old model's split, and ADX <= 20 inside the v2 trades.
B. Vol targeting at the portfolio level. v2 trades, one unit of risk per trade,
   daily mark to market from the bars. Each new trade is scaled by
   target / realized vol of the unscaled book over the last N days (clipped to
   0.25 to 4). N chosen on 2008 to 2016 from 20, 60, 120 by Sharpe; one test on
   2017 to 2026: Sharpe (vol targeted) minus Sharpe (flat), quarter block
   bootstrap, z 1.64. Max drawdown and the leverage range are reported.
C. Chandelier 3 ATR exit inside the stop rule subset (previous bar stop <= 2.5
   ATR) of the v2 trades. Test: paired R(chandelier) minus R(engine), holdout,
   quarter block bootstrap, z 1.64.

Inputs: research/intrabar/signals.csv (research_exits.py), research/confluence_trades.csv
(research_confluence.py), v2_config.json. Caveat printed in the report: this is
another look at the 2017 to 2026 holdout.

Usage (repo folder):  python3 research_v3_studies.py DATA_DIR
Writes research/v3_studies_report.md.
"""
import os, sys, csv, json, math
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import load_series, ema, atr
from batch_backtest import build_catalog
from research_model import load as load_rows, featurize, NAMES, RIDGE, SPLIT_YEAR, block_diff
from research_exits import block_t, exit_engine

OUT = "research"; Z = 1.64; LOOKBACKS = [20, 60, 120]; STOP_MAX = 2.5


def fit(X, y, ridge=RIDGE):
    lo, hi = np.percentile(X, 1, axis=0), np.percentile(X, 99, axis=0); Xc = np.clip(X, lo, hi)
    mu, sd = Xc.mean(0), Xc.std(0) + 1e-9
    def z(M): return np.clip((np.clip(M, lo, hi) - mu) / sd, -5, 5)
    Z1 = np.hstack([z(X), np.ones((len(X), 1))]); reg = ridge * np.eye(Z1.shape[1]); reg[-1, -1] = 0
    w = np.linalg.solve(Z1.T @ Z1 + reg, Z1.T @ y)
    return lambda M: np.hstack([z(M), np.ones((len(M), 1))]) @ w, w


def sharpe(daily):
    d = np.asarray(daily, float); return float(d.mean() / d.std() * math.sqrt(252)) if len(d) > 20 and d.std() > 0 else float("nan")


def maxdd(daily):
    c = np.cumsum(daily); return float(np.max(np.maximum.accumulate(c) - c)) if len(c) else 0.0


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    cat = build_catalog(args[0]); cfg = json.load(open("v2_config.json")); cheap = set(cfg["cheap"])
    rows = load_rows()
    raw = {(r["symbol"], r["entry_time"].replace("T", " ")[:16]): r for r in csv.DictReader(open(os.path.join(OUT, "intrabar", "signals.csv"))) if r["why_engine"] != "skipped"}
    conf = {(r["symbol"], r["entry_time"].replace("T", " ")[:16]): r for r in csv.DictReader(open(os.path.join(OUT, "confluence_trades.csv")))}
    # rows from research_model.load carry no entry_time; rebuild the key from the raw file order (same filter, same order)
    keys = list(raw)
    assert len(keys) == len(rows), "signals.csv changed between loads"
    for r, k in zip(rows, keys):
        r["key"] = k; r["entry_time"] = k[1]; c = conf.get(k)
        r["adx"] = float(c["adx"]) if c else float("nan"); r["breadth"] = float(c["breadth"]) if c else 0.0; r["clu"] = float(c["cluster"]) if c else 0.0
        rr = raw[k]; r["R_ch"] = float(rr["R_chandelier_3atr"]) if rr["R_chandelier_3atr"] != "" else float("nan")
        r["entry"] = float(rr["entry"]); r["stop0"] = float(rr["stop0"]); r["gross"] = float(rr["gross_engine"])
    expl = [r for r in rows if r["year"] < SPLIT_YEAR]; hold = [r for r in rows if r["year"] >= SPLIT_YEAR]
    L = ["# v3 studies: tier model with ADX and breadth, vol targeting, chandelier in the stop rule subset\n",
         f"{len(expl)} exploration trades (2008 to {SPLIT_YEAR - 1}), {len(hold)} holdout trades. Three preregistered tests, one sided z {Z}. "
         "This is one more look at the holdout; count it.\n"]

    # ---- old model and v2 gate
    Xe = np.array([featurize(r) for r in expl], float); Xe[~np.isfinite(Xe)] = 0; ye = np.array([r["net"] for r in expl])
    Xh = np.array([featurize(r) for r in hold], float); Xh[~np.isfinite(Xh)] = 0; yh = np.array([r["net"] for r in hold])
    old, _ = fit(Xe, ye); cut_old = float(np.median(old(Xe)))
    for r, s in zip(expl, old(Xe)): r["old"] = float(s)
    for r, s in zip(hold, old(Xh)): r["old"] = float(s)
    for r in rows: r["v2"] = r["symbol"] in cheap and r["old"] >= cut_old
    v2e = [r for r in expl if r["v2"]]; v2h = [r for r in hold if r["v2"]]
    L.append(f"v2 gate reproduced here: {len(v2e)} exploration and {len(v2h)} holdout trades, holdout avgR {np.mean([r['net'] for r in v2h]):+.4f}.\n")

    # ---- A. new model
    def feat_new(r): return featurize(r) + [r["adx"] if np.isfinite(r["adx"]) else 20.0, r["breadth"], r["clu"]]
    Xe2 = np.array([feat_new(r) for r in expl], float); Xe2[~np.isfinite(Xe2)] = 0
    Xh2 = np.array([feat_new(r) for r in hold], float); Xh2[~np.isfinite(Xh2)] = 0
    new, w2 = fit(Xe2, ye)
    for r, s in zip(expl, new(Xe2)): r["new"] = float(s)
    for r, s in zip(hold, new(Xh2)): r["new"] = float(s)
    cut_new = float(np.median([r["new"] for r in v2e]))
    yv = np.array([r["net"] for r in v2h]); qv = np.array([r["quarter"] for r in v2h])
    keep = np.array([r["new"] >= cut_new for r in v2h]); dA, tA = block_diff(yv, keep, qv)
    keep_adx = np.array([r["adx"] <= 20 for r in v2h]); dX, tX = block_diff(yv, keep_adx, qv)
    cut_old_v2 = float(np.median([r["old"] for r in v2e])); keep_old = np.array([r["old"] >= cut_old_v2 for r in v2h]); dO, tO = block_diff(yv, keep_old, qv)
    L += ["## A. Tier model refit with ADX, breadth, cluster breadth\n",
          "| split of the v2 holdout trades | kept n, avgR | rest n, avgR | diff | boot t | verdict |", "|---|---|---|---|---|---|",
          f"| **new score >= exploration v2 median (the test)** | {keep.sum()}, {yv[keep].mean():+.4f} | {(~keep).sum()}, {yv[~keep].mean():+.4f} | {dA:+.4f} | {tA:.2f} | **{'PASS' if tA > Z else 'no'}** |",
          f"| old score >= exploration v2 median (reference) | {keep_old.sum()}, {yv[keep_old].mean():+.4f} | {(~keep_old).sum()}, {yv[~keep_old].mean():+.4f} | {dO:+.4f} | {tO:.2f} | reference |",
          f"| ADX <= 20 (reference) | {keep_adx.sum()}, {yv[keep_adx].mean():+.4f} | {(~keep_adx).sum()}, {yv[~keep_adx].mean():+.4f} | {dX:+.4f} | {tX:.2f} | reference |",
          "\nNew model weights (per std, exploration fit): " + ", ".join(f"{n} {ww:+.3f}" for n, ww in sorted(zip(NAMES + ["adx", "breadth", "cluster"], w2[:-1]), key=lambda x: -abs(x[1]))[:10]) + "\n"]

    # ---- B. vol targeting: daily marks for v2 trades
    by_sym = defaultdict(list)
    for r in rows:
        if r["v2"]: by_sym[r["symbol"]].append(r)
    daily = defaultdict(float); trade_days = {}
    for s, rs in by_sym.items():
        if s not in cat: continue
        T, O, H, L_, C = load_series(cat[s]); days = np.array([int(t // 86400) for t in T])
        D = dict(O=O, H=H, L=L_, C=C, e21=ema(C, 21), e200=ema(C, 200), A=atr(H, L_, C, 14))
        for r in rs:
            ts = int(datetime.strptime(r["entry_time"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
            t0 = int(np.searchsorted(T, ts)); rpx = abs(r["entry"] - r["stop0"]); d = r["dir"]
            if t0 >= len(T) - 1 or rpx <= 0: continue
            t1, exit_px, _, _ = exit_engine(D, dict(t0=t0, dir=d, entry=r["entry"], stop0=r["stop0"])); t1 = min(int(t1), len(T) - 1)
            if t1 <= t0: continue
            mark = r["entry"]; path = []
            for k in range(t0, t1 + 1):
                last_of_day = (k == t1) or (days[k + 1] != days[k])
                if last_of_day:
                    px = exit_px if k == t1 else C[k]; path.append((days[k], d * (px - mark) / rpx)); mark = px
            path[-1] = (path[-1][0], path[-1][1] - r["cost"])
            r["path"] = path; r["day0"] = days[t0]
            for dd, v in path: daily[dd] += v
    all_days = np.array(sorted(daily)); flat = np.array([daily[d] for d in all_days]); day_ix = {d: i for i, d in enumerate(all_days)}
    yr_of = lambda d: datetime.fromtimestamp(d * 86400, timezone.utc).year
    years = np.array([yr_of(d) for d in all_days]); is_hold = years >= SPLIT_YEAR
    L += ["## B. Vol targeting\n", "| set | book | Sharpe | max DD (R units) | total R | leverage min/median/max |", "|---|---|---|---|---|---|"]
    res = {}
    for N in LOOKBACKS:
        vol = np.array([flat[max(0, i - N):i].std() if i >= 20 else np.nan for i in range(len(flat))])
        target = float(np.nanmedian(vol[~is_hold])); lev = np.clip(target / np.where(np.isnan(vol) | (vol <= 0), target, vol), 0.25, 4.0)
        scaled = np.zeros(len(flat)); levs = []
        for r in rows:
            if not r.get("path"): continue
            f = float(lev[day_ix[r["day0"]]]); levs.append((r["year"] >= SPLIT_YEAR, f))
            for dd, v in r["path"]: scaled[day_ix[dd]] += f * v
        res[N] = (scaled, levs)
    for pname, m in (("explore", ~is_hold), ("holdout", is_hold)):
        L.append(f"| {pname} | flat, one unit per trade | {sharpe(flat[m]):.2f} | {maxdd(flat[m]):.1f} | {flat[m].sum():+.0f} | 1 / 1 / 1 |")
        for N in LOOKBACKS:
            sc, levs = res[N]; lv = [f for h, f in levs if h == (pname == "holdout")]
            L.append(f"| {pname} | vol target, {N} day lookback | {sharpe(sc[m]):.2f} | {maxdd(sc[m]):.1f} | {sc[m].sum():+.0f} | {min(lv):.2f} / {np.median(lv):.2f} / {max(lv):.2f} |")
    bestN = max(LOOKBACKS, key=lambda N: sharpe(res[N][0][~is_hold]))
    sc = res[bestN][0]; qtr = np.array([yr_of(d) * 4 + (datetime.fromtimestamp(d * 86400, timezone.utc).month - 1) // 3 for d in all_days])
    hq = sorted(set(qtr[is_hold])); rng = np.random.default_rng(11); diffs = []
    for _ in range(400):
        pick = rng.integers(0, len(hq), len(hq)); idx = np.concatenate([np.where(qtr == hq[i])[0] for i in pick])
        diffs.append(sharpe(sc[idx]) - sharpe(flat[idx]))
    dS = sharpe(sc[is_hold]) - sharpe(flat[is_hold]); tS = dS / np.std(diffs) if np.std(diffs) > 0 else float("nan")
    L.append(f"\nBest lookback on exploration: **{bestN} days**. Holdout Sharpe difference vs flat: **{dS:+.2f}, boot t {tS:.2f} -> {'PASS' if tS > Z else 'no'}**. "
             "Leverage is relative to one unit of risk per trade; a median near 1 means the target matched the exploration vol.\n")

    # ---- C. chandelier inside the stop rule subset
    sub = [r for r in v2h if r["p_risk_atr"] <= STOP_MAX and np.isfinite(r["R_ch"])]
    pairs = [r["R_ch"] - r["net"] for r in sub]; qs = [r["quarter"] for r in sub]; dC, tC = block_t(pairs, qs)
    sub_all = [r for r in v2h if np.isfinite(r["R_ch"])]; dAll, tAll = block_t([r["R_ch"] - r["net"] for r in sub_all], [r["quarter"] for r in sub_all])
    L += ["## C. Chandelier 3 ATR exit, v2 holdout trades\n", "| subset | n | engine avgR | chandelier avgR | paired diff | boot t | verdict |", "|---|---|---|---|---|---|---|",
          f"| **stop <= {STOP_MAX} ATR (the test)** | {len(sub)} | {np.mean([r['net'] for r in sub]):+.4f} | {np.mean([r['R_ch'] for r in sub]):+.4f} | {dC:+.4f} | {tC:.2f} | **{'PASS' if tC > Z else 'no'}** |",
          f"| all v2 (reference) | {len(sub_all)} | {np.mean([r['net'] for r in sub_all]):+.4f} | {np.mean([r['R_ch'] for r in sub_all]):+.4f} | {dAll:+.4f} | {tAll:.2f} | reference |"]
    open(os.path.join(OUT, "v3_studies_report.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}/v3_studies_report.md")


if __name__ == "__main__":
    main()
