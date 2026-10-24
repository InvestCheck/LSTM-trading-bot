#!/usr/bin/env python3
"""Confluence filters on the engine's trades: do standard indicators or other
breaks, measured on the bar BEFORE entry (known when the resting order is placed,
no lookahead), separate good breaks from bad ones?

Input: research/intrabar/signals.csv from research_exits.py (engine trades =
rows with why_engine != skipped, R_engine net of costs). Features added here, all
on bar t-1 and signed by trade direction where it makes sense:
  adx        ADX(14) on hourly bars
  macd       MACD(12,26,9) histogram sign aligned with the trade (+1/-1)
  rsi        RSI(14) on the trade's side of 50 (+1/-1)
  e50_slope  50 EMA slope over 20 bars aligned (+1/-1)
  htf        close vs 1000 bar EMA (about two months, a higher timeframe trend) aligned
  breadth    engine entries in the same direction on OTHER instruments in the last 24 bars
  cluster    the same, same asset cluster, last 48 bars

Preregistered: FILTERS below, fixed before running. For each, in minus out avgR
on 2008 to 2016 with a quarter block bootstrap; the best filter on exploration
is the one test on 2017 to 2026 (one sided z 1.64, and it must keep at least 25%
of trades). Everything else is reference.

Usage (repo folder):  python3 research_confluence.py DATA_DIR
Writes research/confluence_report.md and research/confluence_trades.csv.
"""
import os, sys, csv
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import load_series, ema
from batch_backtest import build_catalog
from research_exits import block_t, summarize

OUT = "research"; SIG = os.path.join(OUT, "intrabar", "signals.csv"); Z = 1.64; MIN_SHARE = 0.25
CLUSTER = {}
for c, syms in {"metals": "GC MGC SI SIR HG PL PA", "energy": "CL BZ B NG HO RB", "index": "ES NQ YM RTY EW NKD NIY FDAX FDXM FESX FXXP FCE FTUK MME MFS",
                "rates": "ZT ZF ZN TN UB FGBL FGBM FGBX FBTP FOAT FBON", "fx": "E6 E7 E1 J1 J7 B6 A6 AD CNH NOK SEK RP RY MP N6 DX",
                "ags": "ZC ZS ZL ZM KE XC RS SB CT HE LE GF DC G FTI"}.items():
    for s in syms.split(): CLUSTER[s] = c
FILTERS = {                       # name: (feature, op, value)
    "adx_ge_20": ("adx", ">=", 20), "adx_ge_25": ("adx", ">=", 25), "adx_le_20": ("adx", "<=", 20),
    "macd_aligned": ("macd", ">=", 1), "rsi_aligned": ("rsi", ">=", 1), "e50_slope_aligned": ("e50_slope", ">=", 1),
    "htf_aligned": ("htf", ">=", 1), "breadth_ge_1": ("breadth", ">=", 1), "cluster_ge_1": ("cluster", ">=", 1),
    "adx20_macd_rsi": ("combo", ">=", 3),
}


def wilder(x, n):
    out = np.zeros_like(x); out[n - 1] = x[:n].mean() if len(x) >= n else 0
    for i in range(n, len(x)): out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def adx14(H, L, C, n=14):
    up = np.diff(H, prepend=H[0]); dn = -np.diff(L, prepend=L[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
    atr = wilder(tr, n); pdi = 100 * wilder(pdm, n) / np.maximum(atr, 1e-12); ndi = 100 * wilder(ndm, n) / np.maximum(atr, 1e-12)
    dx = 100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12); return wilder(dx, n)


def rsi14(C, n=14):
    d = np.diff(C, prepend=C[0]); g = wilder(np.maximum(d, 0), n); l = wilder(np.maximum(-d, 0), n)
    return 100 - 100 / (1 + g / np.maximum(l, 1e-12))


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    cat = build_catalog(args[0])
    rows = [r for r in csv.DictReader(open(SIG)) if r["why_engine"] != "skipped"]
    for r in rows:
        r["dir"] = int(r["dir"]); r["R"] = float(r["R_engine"]); r["quarter"] = int(r["quarter"])
        r["ts"] = int(datetime.strptime(r["entry_time"].replace("T", " ")[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
        r["year"] = datetime.fromtimestamp(r["ts"], timezone.utc).year
    by_sym = defaultdict(list)
    for r in rows: by_sym[r["symbol"]].append(r)
    for s, rs in by_sym.items():
        if s not in cat: print(f"{s:5s} missing"); continue
        T, O, H, L, C = load_series(cat[s])
        adx = adx14(H, L, C); rsi = rsi14(C); e12, e26, e50, e1000 = ema(C, 12), ema(C, 26), ema(C, 50), ema(C, 1000)
        macd = e12 - e26; sig = ema(macd, 9); hist = macd - sig
        for r in rs:
            t = int(np.searchsorted(T, r["ts"])); p = max(1, t - 1); d = r["dir"]
            r["adx"] = round(float(adx[p]), 2); r["macd"] = int(np.sign(hist[p]) * d); r["rsi"] = 1 if (rsi[p] - 50) * d > 0 else -1
            r["e50_slope"] = int(np.sign(e50[p] - e50[max(0, p - 20)]) * d); r["htf"] = int(np.sign(C[p] - e1000[p]) * d)
            r["combo"] = int(r["adx"] >= 20) + int(r["macd"] >= 1) + int(r["rsi"] >= 1)
        print(f"{s:5s} {len(rs)} trades", flush=True)
    rows = [r for r in rows if "adx" in r]
    # breadth: other instruments' engine entries in the same direction shortly before this one
    by_dir = {d: sorted([(r["ts"], r["symbol"]) for r in rows if r["dir"] == d]) for d in (1, -1)}
    for r in rows:
        lst = by_dir[r["dir"]]; ts = np.array([x[0] for x in lst]); lo = int(np.searchsorted(ts, r["ts"] - 48 * 3600)); hi = int(np.searchsorted(ts, r["ts"], side="left"))
        win = [x for x in lst[lo:hi] if x[1] != r["symbol"]]
        r["breadth"] = len({x[1] for x in win if x[0] >= r["ts"] - 24 * 3600}); r["cluster"] = len({x[1] for x in win if CLUSTER.get(x[1]) == CLUSTER.get(r["symbol"], "?")})
    with open(os.path.join(OUT, "confluence_trades.csv"), "w", newline="") as fh:
        keys = ["symbol", "entry_time", "dir", "R", "year", "quarter", "adx", "macd", "rsi", "e50_slope", "htf", "breadth", "cluster", "combo"]
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    def keep(r, feat, op, val):
        x = r[feat]; return x >= val if op == ">=" else x <= val

    def test(sub, feat, op, val):
        inn = [r for r in sub if keep(r, feat, op, val)]; out = [r for r in sub if not keep(r, feat, op, val)]
        si, so = summarize([r["R"] for r in inn]), summarize([r["R"] for r in out])
        by_q = defaultdict(list)
        for r in sub: by_q[r["quarter"]].append((r["R"], keep(r, feat, op, val)))
        keys = list(by_q); rng = np.random.default_rng(7); diffs = []
        for _ in range(400):
            pick = rng.integers(0, len(keys), len(keys))
            a = [v for i in pick for v, k in by_q[keys[i]] if k]; b = [v for i in pick for v, k in by_q[keys[i]] if not k]
            if a and b: diffs.append(np.mean(a) - np.mean(b))
        diff = si["avgR"] - so["avgR"]; sd = float(np.std(diffs)) if diffs else float("nan")
        return si, so, diff, (diff / sd if sd and sd > 0 else float("nan")), si["n"] / max(1, len(sub))

    L = ["# Confluence filters on the engine's trades (features on the bar before entry, no lookahead)\n",
         f"{len(rows)} engine trades. in = trades the filter keeps. One preregistered test: best filter on 2008 to 2016 by in minus out t, "
         f"tested on 2017 to 2026 (z {Z}, keep at least {MIN_SHARE:.0%}).\n",
         "| set | filter | in: n, avgR, win% | out: n, avgR, win% | in minus out | boot t | kept |", "|---|---|---|---|---|---|---|"]
    best = None
    for pname, cond in (("explore 2008-2016", lambda r: r["year"] < 2017), ("holdout 2017-2026", lambda r: r["year"] >= 2017)):
        sub = [r for r in rows if cond(r)]
        for name, (feat, op, val) in FILTERS.items():
            si, so, diff, t, share = test(sub, feat, op, val)
            L.append(f"| {pname} | {name} | {si['n']}, {si['avgR']:+.4f}, {si['win']:.0f}% | {so['n']}, {so['avgR']:+.4f}, {so['win']:.0f}% | {diff:+.4f} | {t:.2f} | {share:.0%} |")
            if pname.startswith("explore") and share >= MIN_SHARE and (best is None or t > best[1]): best = (name, t)
    L.append("\n## Feature summary, holdout (avgR by quartile of the continuous features; sign features by value)\n")
    hold = [r for r in rows if r["year"] >= 2017]
    for feat in ("adx", "breadth", "cluster"):
        xs = np.array([r[feat] for r in hold], float); rs = np.array([r["R"] for r in hold]); qs = np.quantile(xs, [0.25, 0.5, 0.75])
        bins = [xs <= qs[0], (xs > qs[0]) & (xs <= qs[1]), (xs > qs[1]) & (xs <= qs[2]), xs > qs[2]]
        L.append(f"- {feat}: " + ", ".join(f"Q{i + 1} {rs[b].mean():+.3f} (n={b.sum()})" for i, b in enumerate(bins) if b.sum()))
    for feat in ("macd", "rsi", "e50_slope", "htf"):
        rs = np.array([r["R"] for r in hold]); xs = np.array([r[feat] for r in hold])
        L.append(f"- {feat}: aligned {rs[xs > 0].mean():+.3f} (n={(xs > 0).sum()}), against {rs[xs < 0].mean():+.3f} (n={(xs < 0).sum()})")
    if best:
        feat, op, val = FILTERS[best[0]]; si, so, diff, t, share = test(hold, feat, op, val)
        L += ["\n## Preregistered test\n", f"Best on exploration: **{best[0]}** (t {best[1]:.2f}).",
              f"Holdout in minus out: **{diff:+.4f}R, t {t:.2f}, keeps {share:.0%} -> {'PASS' if (t > Z and share >= MIN_SHARE) else 'no'}**."]
    open(os.path.join(OUT, "confluence_report.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}/confluence_report.md")


if __name__ == "__main__":
    main()
