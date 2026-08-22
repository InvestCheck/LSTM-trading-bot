#!/usr/bin/env python3
"""Statistics that do not assume trades are independent.

The published t-statistics in the 131-instrument scan treat every trade as an
independent draw. They are not. A trendline-walk strategy on a trending
instrument fires repeatedly in the same direction inside a single macro move,
so the trade series is strongly autocorrelated and the naive t is inflated.
This module provides the three corrections used in the stage-2 holdout:

  block_bootstrap   t-statistic under a block-resampling null that preserves
                    serial dependence. Reports the inflation factor of the
                    naive t.
  deflated_sharpe   Bailey / Lopez de Prado deflated Sharpe ratio, which prices
                    in the fact that the winner was chosen out of N trials.
  hac_ols           OLS with Newey-West standard errors, used to test whether
                    trade returns are just beta to the prevailing trend.

Nothing here refits the trading rule. These are diagnostics applied to an
already-frozen set of trade returns.
"""
import csv
import math
from datetime import datetime, timezone

import numpy as np

EULER = 0.5772156649015329


# ---------------------------------------------------------------- trade I/O

def load_trades(path, symbol=None):
    """Read a backtests/trades_<SYM>.csv written by batch_backtest.write_trades.

    Returns (times, R, dirs) with times as epoch seconds of the ENTRY bar,
    sorted ascending. Only the entry time and realised R are needed; every
    other column is signal-time metadata or outcome detail.
    """
    ts, r, d = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if symbol and row["symbol"] != symbol:
                continue
            ts.append(_epoch(row["entry_time"]))
            r.append(float(row["R_realized"]))
            d.append(int(row["dir"]))
    if not ts:
        raise ValueError(f"no trades parsed from {path}")
    idx = np.argsort(ts)
    return np.array(ts)[idx], np.array(r, float)[idx], np.array(d, int)[idx]


def _epoch(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    return int(float(s))


def split_at(times, cutoff_epoch):
    """Boolean masks (pre, post) for a single calendar cutoff."""
    pre = times < cutoff_epoch
    return pre, ~pre


def naive_t(x):
    """The t-statistic as published: mean / (sd / sqrt(n)), iid assumption."""
    x = np.asarray(x, float)
    if x.size < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(x.size)))


def profit_factor(x):
    x = np.asarray(x, float)
    w, l = x[x > 0.01].sum(), abs(x[x < -0.01].sum())
    return float(w / l) if l > 0 else float("inf")


# ------------------------------------------------------------ block bootstrap

def calendar_blocks(times, freq):
    """Group trade indices into calendar blocks.

    freq is one of {'month', 'quarter', 'year'}. Blocks are contiguous in time
    and variable in length, which is the point: a block is a stretch of market
    over which the strategy's trades share a regime, not a fixed count.
    """
    keys = []
    for t in times:
        dt = datetime.fromtimestamp(int(t), timezone.utc)
        if freq == "month":
            keys.append((dt.year, dt.month))
        elif freq == "quarter":
            keys.append((dt.year, (dt.month - 1) // 3))
        elif freq == "year":
            keys.append((dt.year,))
        else:
            raise ValueError(f"freq must be month, quarter or year, got {freq!r}")
    blocks, cur, prev = [], [], None
    for i, k in enumerate(keys):
        if prev is not None and k != prev:
            blocks.append(np.array(cur))
            cur = []
        cur.append(i)
        prev = k
    blocks.append(np.array(cur))
    return blocks


def fixed_blocks(n, length):
    """Circular moving blocks of a fixed number of trades."""
    starts = np.arange(n)
    return [np.arange(s, s + length) % n for s in starts]


def block_bootstrap(x, blocks, B=10000, seed=0):
    """Bootstrap-t under a null of zero mean, resampling whole blocks.

    The series is demeaned, then blocks are drawn with replacement until the
    resample is at least as long as the original and truncated to length n.
    Because whole blocks move together, the resampled series keeps the
    within-block dependence of the real trade stream.

    Returns a dict with the observed t, the bootstrap p-value, the standard
    deviation of the bootstrap t distribution, and the inflation factor. Under
    genuine independence sd_boot is close to 1.0 and inflation is close to 1.0;
    values well above 1 mean the naive t is overstated by that multiple.
    """
    x = np.asarray(x, float)
    n = x.size
    t_obs = naive_t(x)
    xc = x - x.mean()
    rng = np.random.default_rng(seed)
    nb = len(blocks)
    # average block length, used to decide how many blocks per resample
    avg_len = max(1.0, n / nb)
    draw = int(math.ceil(n / avg_len)) + 2

    ts = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, nb, size=draw)
        y = np.concatenate([xc[blocks[j]] for j in pick])[:n]
        sd = y.std(ddof=1)
        ts[b] = y.mean() / (sd / math.sqrt(y.size)) if sd > 0 else 0.0

    sd_boot = float(ts.std(ddof=1))
    p = float(np.mean(np.abs(ts) >= abs(t_obs)))
    return dict(n=n, n_blocks=nb, t_naive=t_obs, sd_boot=sd_boot,
                inflation=sd_boot, t_adj=t_obs / sd_boot if sd_boot > 0 else float("nan"),
                p_boot=p, n_eff=n / (sd_boot ** 2) if sd_boot > 0 else float("nan"))


# ------------------------------------------------------------ deflated Sharpe

def expected_max_sharpe(var_sr, n_trials):
    """Expected maximum Sharpe across n_trials independent strategies whose
    true Sharpe is zero and whose estimates have variance var_sr.

    This is the benchmark the winner must beat. Picking the best of 131 scans
    and comparing it to zero is the error this corrects.
    """
    if n_trials < 2:
        return 0.0
    from statistics import NormalDist
    nd = NormalDist()
    a = nd.inv_cdf(1 - 1.0 / n_trials)
    b = nd.inv_cdf(1 - 1.0 / (n_trials * math.e))
    return math.sqrt(var_sr) * ((1 - EULER) * a + EULER * b)


def deflated_sharpe(x, n_trials, var_sr, sr_benchmark=None):
    """Bailey and Lopez de Prado (2014) deflated Sharpe ratio.

    x is the per-trade R series of the selected strategy. var_sr is the
    variance of the per-trade Sharpe estimates ACROSS the trials that were
    searched, which for this repo comes from the 131-instrument scan file.
    Returns the probability that the true Sharpe exceeds the benchmark.
    A DSR below about 0.95 means the result is not distinguishable from the
    best of N noisy searches.
    """
    from statistics import NormalDist
    x = np.asarray(x, float)
    n = x.size
    sd = x.std(ddof=1)
    if n < 4 or sd == 0:
        return dict(sr=float("nan"), sr0=float("nan"), dsr=float("nan"))
    sr = x.mean() / sd
    z = (x - x.mean()) / sd
    g3 = float((z ** 3).mean())
    g4 = float((z ** 4).mean())
    sr0 = expected_max_sharpe(var_sr, n_trials) if sr_benchmark is None else sr_benchmark
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + 0.25 * (g4 - 1) * sr ** 2))
    stat = (sr - sr0) * math.sqrt(n - 1) / denom
    return dict(sr=sr, sr0=sr0, skew=g3, kurt=g4, stat=stat,
                dsr=NormalDist().cdf(stat), psr_vs_zero=NormalDist().cdf(
                    sr * math.sqrt(n - 1) / denom))


def sharpe_variance_from_scan(scan_csv, config_contains="intrabar"):
    """Variance of per-trade Sharpe across the scanned instruments.

    Reads results/scan_results_long_*.csv. Per-trade Sharpe is recovered as
    tstat / sqrt(trades), which is exact given how tstat was computed.
    """
    srs = []
    with open(scan_csv, newline="") as f:
        for row in csv.DictReader(f):
            if config_contains not in row.get("config", ""):
                continue
            try:
                n, t = int(row["trades"]), float(row["tstat"])
            except (ValueError, KeyError):
                continue
            if n > 1:
                srs.append(t / math.sqrt(n))
    if len(srs) < 2:
        raise ValueError(f"only {len(srs)} usable rows in {scan_csv}; "
                         f"check the config_contains filter")
    return float(np.var(srs, ddof=1)), len(srs)


def bonferroni_t(n_tests, alpha=0.05, two_sided=True):
    from statistics import NormalDist
    a = alpha / n_tests / (2 if two_sided else 1)
    return NormalDist().inv_cdf(1 - a)


# ------------------------------------------------------------- HAC regression

def hac_ols(y, X, lags=None):
    """OLS with Newey-West standard errors.

    X should already include a constant column. lags defaults to the usual
    floor(4 * (n/100)^(2/9)) rule. Returns coefficients, HAC standard errors
    and t-statistics.
    """
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    n, k = X.shape
    if lags is None:
        lags = int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta

    u = X * resid[:, None]
    S = u.T @ u
    for l in range(1, lags + 1):
        w = 1.0 - l / (lags + 1.0)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    return dict(beta=beta, se=se, t=t, lags=lags, n=n, resid=resid)
