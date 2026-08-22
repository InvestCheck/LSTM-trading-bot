#!/usr/bin/env python3
"""Stage-2 holdout: selection frozen on pre-cutoff data only.

WHY THIS EXISTS
---------------
Stage 1 (`holdout_protocol.md`) split the trades of four survivors at
2020-01-01 and scored the post-2020 half. That split is contaminated, and the
protocol's own warning understates by how much. The four symbols were selected
because their FULL-SAMPLE t exceeded 3, and the full sample contains the
holdout. The share of the selection statistic that is literally the holdout is
sqrt(n_post / n_full):

    J7  0.62      J1  0.61      PA  0.53      ZR  0.45

So roughly 60% of the evidence that chose J7 and J1 was the very data used to
confirm them. That is not a weak out-of-sample test, it is a partly circular
one.

The fix is to run the selection itself on pre-cutoff data only, freeze the
resulting symbol list to disk before looking at anything else, and then score
the post-cutoff period once. Under a Bonferroni threshold of t > 3.55 for 131
tests, the pre-2020 t-statistics were J7 3.95, J1 2.36, PA 3.47, ZR 3.06, so
this procedure is expected to select J7 alone. J1 and ZR were never survivors
on data a trader would actually have had in hand at the start of 2020.

    select     partition every trades_<SYM>.csv at the cutoff, rank on the PRE
               period, apply the threshold, write a frozen selection file
    score      read the frozen file, score the POST period for those symbols
               only, apply the pre-registered pass criteria
    bootstrap  block-resample a symbol's trades to get a t that does not assume
               independence, swept over month / quarter / year blocks
    dsr        deflated Sharpe against the best-of-131 benchmark
    regime     regress trade returns on the prevailing trend, to separate
               trendline geometry from plain trend beta

Run `select` and `score` in that order, on separate days if you can stand it.
`select` refuses to overwrite an existing frozen file without --force, and
--force is recorded in the file so a re-selection cannot be passed off as the
original one.

Usage:
  python3 batch_backtest.py --slip 1            # all 131, writes backtests/
  python3 holdout_stage2.py select
  python3 holdout_stage2.py score
  python3 holdout_stage2.py bootstrap J7 --period post
  python3 holdout_stage2.py dsr J7 --period post
  python3 holdout_stage2.py regime J7 --lookback 480
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

from stats_honest import (block_bootstrap, bonferroni_t, calendar_blocks,
                          deflated_sharpe, hac_ols, load_trades, naive_t,
                          profit_factor, sharpe_variance_from_scan, split_at)

TRADE_DIR = "backtests"
RESULT_DIR = "results"
SEED_DIR = "seed"
CUTOFF = "2020-01-01"
N_TESTS = 131
ALPHA = 0.05

# Pre-registered pass criteria for the post-cutoff period. Stored inside the
# frozen selection file so that `score` reads them from disk rather than from
# whatever this source file happens to say later.
CRITERIA = dict(pass_pf=1.2, pass_t=2.0, marginal_pf=1.1, marginal_t=1.5)


def cutoff_epoch(s):
    return int(datetime.strptime(s, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def all_symbols():
    return sorted(os.path.basename(p)[len("trades_"):-len(".csv")]
                  for p in glob.glob(os.path.join(TRADE_DIR, "trades_*.csv")))


def stats(x):
    x = np.asarray(x, float)
    if x.size == 0:
        return dict(n=0, PF=float("nan"), avgR=float("nan"),
                    totalR=0.0, sd=float("nan"), t=float("nan"))
    return dict(n=int(x.size), PF=profit_factor(x), avgR=float(x.mean()),
                totalR=float(x.sum()), sd=float(x.std(ddof=1)) if x.size > 1 else float("nan"),
                t=naive_t(x))


# ------------------------------------------------------------------- select

def cmd_select(a):
    path = os.path.join(RESULT_DIR, f"selection_pre{a.cutoff}.json")
    if os.path.exists(path) and not a.force:
        sys.exit(f"{path} already exists. The whole point of this file is that "
                 f"it is written once, before the holdout is looked at. Use "
                 f"--force only if you are prepared to say so in the README.")

    ce = cutoff_epoch(a.cutoff)
    thr = bonferroni_t(a.n_tests, a.alpha)
    syms = a.symbols or all_symbols()
    if not syms:
        sys.exit(f"no trades_*.csv in {TRADE_DIR}/. run batch_backtest.py first.")

    rows = []
    for s in syms:
        p = os.path.join(TRADE_DIR, f"trades_{s}.csv")
        if not os.path.exists(p):
            print(f"  {s:6s} missing {p}", file=sys.stderr)
            continue
        times, R, _ = load_trades(p)
        pre, _ = split_at(times, ce)
        st = stats(R[pre])
        st["symbol"] = s
        rows.append(st)

    rows.sort(key=lambda r: -r["t"] if r["t"] == r["t"] else float("inf"))
    picked = {r["symbol"] for r in rows
              if r["t"] == r["t"] and r["t"] > thr and r["n"] >= a.min_trades}

    print(f"selection on entries before {a.cutoff}, {len(rows)} instruments scanned")
    print(f"Bonferroni threshold for {a.n_tests} tests at alpha {a.alpha}: t > {thr:.2f}")
    print(f"minimum trades to be eligible: {a.min_trades}\n")
    hdr = f"{'symbol':8s} {'n':>6s} {'PF':>6s} {'avgR':>7s} {'totalR':>9s} {'t':>6s}   verdict"
    print(hdr); print("-" * len(hdr))
    for r in rows[:a.show]:
        v = "SELECTED" if r["symbol"] in picked else ""
        print(f"{r['symbol']:8s} {r['n']:6d} {r['PF']:6.2f} {r['avgR']:+7.3f} "
              f"{r['totalR']:+9.1f} {r['t']:6.2f}   {v}")
    print("-" * len(hdr))
    order = [r['symbol'] for r in rows if r['symbol'] in picked]
    print(f"selected: {', '.join(order) or '(none)'}")

    if not picked:
        print("\nNo instrument clears the threshold on pre-cutoff data alone. "
              "That is the result. There is nothing to score in stage 2 and the "
              "README should say so.")

    os.makedirs(RESULT_DIR, exist_ok=True)
    payload = dict(
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        cutoff=a.cutoff, n_tests=a.n_tests, alpha=a.alpha, threshold_t=thr,
        min_trades=a.min_trades, forced=bool(a.force),
        criteria=CRITERIA,
        selected=order,
        pre_period_stats={r["symbol"]: r for r in rows},
        trade_file_hashes={r["symbol"]: _sha(os.path.join(TRADE_DIR, f"trades_{r['symbol']}.csv"))
                           for r in rows},
    )
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    print(f"\nfrozen -> {path}")
    print("Commit this file before running `score`.")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# -------------------------------------------------------------------- score

def cmd_score(a):
    path = os.path.join(RESULT_DIR, f"selection_pre{a.cutoff}.json")
    if not os.path.exists(path):
        sys.exit(f"{path} not found. run `select` first, and commit it.")
    sel = json.load(open(path))
    if sel.get("forced"):
        print("NOTE: this selection file was written with --force. It is not a "
              "clean pre-registration and must be described that way.\n",
              file=sys.stderr)

    ce = cutoff_epoch(sel["cutoff"])
    c = sel["criteria"]
    syms = sel["selected"]
    if not syms:
        sys.exit("the frozen selection is empty. nothing to score.")

    out, changed = [], []
    hdr = (f"{'symbol':8s} {'period':22s} {'n':>6s} {'PF':>6s} {'avgR':>7s} "
           f"{'totalR':>9s} {'t':>6s}  verdict")
    print(f"scoring the frozen selection from {sel['created_utc']}")
    print(f"selected on pre-{sel['cutoff']} data at t > {sel['threshold_t']:.2f}: "
          f"{', '.join(syms)}\n")
    print(hdr); print("-" * len(hdr))
    for s in syms:
        p = os.path.join(TRADE_DIR, f"trades_{s}.csv")
        if _sha(p) != sel["trade_file_hashes"].get(s):
            changed.append(s)
        times, R, _ = load_trades(p)
        pre, post = split_at(times, ce)
        for label, mask in (("pre (selection)", pre), ("post (HOLDOUT)", post)):
            st = stats(R[mask])
            v = ""
            if label.startswith("post"):
                if st["PF"] > c["pass_pf"] and st["t"] > c["pass_t"]:
                    v = "PASS"
                elif st["PF"] > c["marginal_pf"] and st["t"] > c["marginal_t"]:
                    v = "MARGINAL"
                else:
                    v = "FAIL"
                st.update(symbol=s, verdict=v)
                out.append(st)
            print(f"{s:8s} {label:22s} {st['n']:6d} {st['PF']:6.2f} {st['avgR']:+7.3f} "
                  f"{st['totalR']:+9.1f} {st['t']:6.2f}  {v}")
    print("-" * len(hdr))

    if changed:
        print(f"\nWARNING: trade files changed since selection: {', '.join(changed)}. "
              f"The backtest was re-run between freezing and scoring, so this is "
              f"not the experiment that was registered.", file=sys.stderr)

    print("\nThe naive t above still assumes independent trades. Run "
          "`bootstrap <SYM> --period post` before believing any of it.")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    op = os.path.join(RESULT_DIR, f"holdout_stage2_{stamp}.csv")
    with open(op, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "n", "PF", "avgR", "totalR",
                                          "sd", "t", "verdict"])
        w.writeheader()
        for r in out:
            w.writerow(r)
    print(f"-> {op}")


# ---------------------------------------------------------------- bootstrap

def _period_mask(times, period, ce):
    pre, post = split_at(times, ce)
    return {"pre": pre, "post": post, "full": np.ones(times.size, bool)}[period]


def cmd_bootstrap(a):
    ce = cutoff_epoch(a.cutoff)
    times, R, _ = load_trades(os.path.join(TRADE_DIR, f"trades_{a.symbol}.csv"))
    m = _period_mask(times, a.period, ce)
    t_, r_ = times[m], R[m]
    if r_.size < 30:
        sys.exit(f"only {r_.size} trades in the {a.period} period; bootstrap is "
                 f"not meaningful at that size.")

    print(f"{a.symbol}  {a.period} period  n={r_.size}  naive t={naive_t(r_):.2f}")
    print(f"{a.draws} resamples, whole blocks drawn with replacement from the "
          f"demeaned series\n")
    hdr = (f"{'blocks':10s} {'count':>6s} {'sd_boot':>8s} {'inflation':>10s} "
           f"{'t_adj':>7s} {'n_eff':>7s} {'p':>8s}")
    print(hdr); print("-" * len(hdr))
    for freq in ("month", "quarter", "year"):
        b = calendar_blocks(t_, freq)
        res = block_bootstrap(r_, b, B=a.draws, seed=a.seed)
        print(f"{freq:10s} {res['n_blocks']:6d} {res['sd_boot']:8.2f} "
              f"{res['inflation']:10.2f} {res['t_adj']:7.2f} {res['n_eff']:7.0f} "
              f"{res['p_boot']:8.4f}")
    print("-" * len(hdr))
    print("sd_boot near 1.0 means the trades really are close to independent "
          "and the naive t stands.\nsd_boot of 2.0 means the naive t is roughly "
          "twice what the evidence supports.\nn_eff is the number of independent "
          "trades the series is actually worth.")


# ---------------------------------------------------------------------- dsr

def cmd_dsr(a):
    ce = cutoff_epoch(a.cutoff)
    times, R, _ = load_trades(os.path.join(TRADE_DIR, f"trades_{a.symbol}.csv"))
    r_ = R[_period_mask(times, a.period, ce)]

    scan = a.scan or _latest("scan_results_long_*.csv")
    var_sr, n_trials = sharpe_variance_from_scan(scan, a.config)
    if a.n_trials:
        n_trials = a.n_trials
    d = deflated_sharpe(r_, n_trials, var_sr)

    print(f"{a.symbol}  {a.period} period  n={r_.size}")
    print(f"trial variance from {os.path.basename(scan)}: {n_trials} trials, "
          f"var(SR) = {var_sr:.6f}\n")
    print(f"  per-trade Sharpe            {d['sr']:+.4f}")
    print(f"  skew / kurtosis             {d['skew']:+.2f} / {d['kurt']:.2f}")
    print(f"  expected max SR under null  {d['sr0']:+.4f}   "
          f"(best of {n_trials} searches, true edge zero)")
    print(f"  PSR vs zero                 {d['psr_vs_zero']:.4f}")
    print(f"  DEFLATED SHARPE             {d['dsr']:.4f}")
    print()
    if d["dsr"] < 0.95:
        print("Below 0.95. Once the size of the search is priced in, this is not "
              "distinguishable from the best of a pile of noisy scans.")
    else:
        print("Above 0.95 against the best-of-N benchmark. Note this still "
              "assumes independent trades; cross-check with `bootstrap`.")


def _latest(pattern):
    hits = sorted(glob.glob(os.path.join(RESULT_DIR, pattern)))
    if not hits:
        sys.exit(f"no {pattern} in {RESULT_DIR}/; pass --scan explicitly.")
    return hits[-1]


# ------------------------------------------------------------------- regime

def cmd_regime(a):
    """Is the edge trendline geometry, or is it just being long a trend?

    For every trade, measure the prevailing trend at entry as a normalised
    trailing move, sign it by the trade's direction, and regress realised R on
    it with Newey-West errors. If the slope is large and the intercept is not
    distinguishable from zero, the strategy is a trend proxy and the specific
    trendline construction is doing no work. For J7 the suspicion is that
    post-2020 is one long yen depreciation and the 570 holdout trades are one
    bet expressed 570 times.
    """
    from backtest_hull import load_series

    ce = cutoff_epoch(a.cutoff)
    times, R, D = load_trades(os.path.join(TRADE_DIR, f"trades_{a.symbol}.csv"))
    m = _period_mask(times, a.period, ce)
    times, R, D = times[m], R[m], D[m]

    seed = a.seed_file or os.path.join(SEED_DIR, f"{a.symbol}.csv")
    if not os.path.exists(seed):
        sys.exit(f"need the price series at {seed} to measure the trend.")
    T, O, H, L, C = load_series(seed)
    lb = a.lookback

    logC = np.log(C)
    ret1 = np.diff(logC, prepend=logC[0])
    trend = np.full(C.size, np.nan)
    for i in range(lb, C.size):
        sd = ret1[i - lb + 1:i + 1].std(ddof=1)
        if sd > 0:
            trend[i] = (logC[i] - logC[i - lb]) / (sd * math.sqrt(lb))

    idx = np.searchsorted(T, times, side="right") - 1
    ok = (idx >= 0) & (idx < C.size)
    z = np.where(ok, trend[np.clip(idx, 0, C.size - 1)], np.nan)
    good = np.isfinite(z) & np.isfinite(R)
    y, x = R[good], (D[good] * z[good])
    if y.size < 30:
        sys.exit(f"only {y.size} trades with a usable trend reading.")

    X = np.column_stack([np.ones(y.size), x])
    res = hac_ols(y, X, lags=a.lags)
    b0, b1 = res["beta"]
    t0, t1 = res["t"]

    print(f"{a.symbol}  {a.period} period  n={y.size}  trend lookback {lb} bars  "
          f"Newey-West lags {res['lags']}\n")
    print(f"  R  =  alpha  +  beta * (direction x normalised trailing trend)\n")
    print(f"  alpha (edge net of trend)   {b0:+.4f}   t = {t0:+.2f}")
    print(f"  beta  (trend loading)       {b1:+.4f}   t = {t1:+.2f}")
    print(f"  mean signed trend at entry  {x.mean():+.3f}")
    print(f"  raw mean R                  {R[good].mean():+.4f}")
    print(f"  share of mean R from trend  {(b1 * x.mean()) / R[good].mean():.1%}"
          if R[good].mean() != 0 else "")
    print()
    if abs(t0) < 2:
        print("The intercept is not distinguishable from zero. Whatever the "
              "trendline detector contributes beyond directional trend exposure "
              "is not measurable here.")


# --------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--cutoff", default=CUTOFF)
        return sp

    s = common(sub.add_parser("select", help="freeze a selection on pre-cutoff data"))
    s.add_argument("symbols", nargs="*")
    s.add_argument("--n-tests", type=int, default=N_TESTS)
    s.add_argument("--alpha", type=float, default=ALPHA)
    s.add_argument("--min-trades", type=int, default=100)
    s.add_argument("--show", type=int, default=25)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_select)

    s = common(sub.add_parser("score", help="score the frozen selection on the holdout"))
    s.set_defaults(func=cmd_score)

    s = common(sub.add_parser("bootstrap", help="block bootstrap t for one symbol"))
    s.add_argument("symbol")
    s.add_argument("--period", default="post", choices=["pre", "post", "full"])
    s.add_argument("--draws", type=int, default=10000)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=cmd_bootstrap)

    s = common(sub.add_parser("dsr", help="deflated Sharpe against best-of-N"))
    s.add_argument("symbol")
    s.add_argument("--period", default="post", choices=["pre", "post", "full"])
    s.add_argument("--scan", default=None)
    s.add_argument("--config", default="intrabar")
    s.add_argument("--n-trials", type=int, default=None)
    s.set_defaults(func=cmd_dsr)

    s = common(sub.add_parser("regime", help="separate trend beta from trendline edge"))
    s.add_argument("symbol")
    s.add_argument("--period", default="post", choices=["pre", "post", "full"])
    s.add_argument("--lookback", type=int, default=480)
    s.add_argument("--lags", type=int, default=None)
    s.add_argument("--seed-file", default=None)
    s.set_defaults(func=cmd_regime)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
