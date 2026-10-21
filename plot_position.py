#!/usr/bin/env python3
"""Draw the chart behind a live position: the cached hourly bars, the trendline the
engine broke, its touches, the entry bar, the initial and current stop, and the stop
anchor line if the stop came from one. Reruns the engine exactly as the bot does, so
the line is the one the bot used.

Usage (repo folder, droplet):  venv/bin/python plot_position.py PA [HG ...] [--bars 400]
Writes plot_<SYMBOL>.png next to the repo; copy it over with
  scp bot@<droplet>:~/trendline-bot-repo/plot_PA.png .
Needs matplotlib: venv/bin/pip install matplotlib
"""
import sys, json
from datetime import datetime, timezone
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

from live_ibkr import run_engine, cache_path, STATE_FILE
from backtest_hull import load_series


def plot_trade(s, op, P, T, O, H, L, C, out, nb=300):
    """Draw one engine trade (open position dict or closed trade dict) to `out`."""
    a, m, t0 = op["a"], op["m"], op["t0"]; kind = op["kind"]; d = op["dir"]; n = len(T)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 11), gridspec_kw=dict(height_ratios=[1, 1.3]))

    def draw(ax, lo, hi, candles):
        x = np.arange(lo, hi + 1)
        if candles:
            up = C[lo:hi + 1] >= O[lo:hi + 1]; col = ["#2a9d8f" if u else "#c0392b" for u in up]
            ax.vlines(x, L[lo:hi + 1], H[lo:hi + 1], colors=col, linewidth=0.8)
            ax.bar(x, (C - O)[lo:hi + 1], bottom=O[lo:hi + 1], width=0.7, color=col, alpha=0.85)
        else:
            ax.fill_between(x, L[lo:hi + 1], H[lo:hi + 1], color="#999999", alpha=0.35, linewidth=0)
            ax.plot(x, C[lo:hi + 1], color="#444444", linewidth=0.8, label="close")
        xl = np.arange(max(a, lo), hi + 1); ax.plot(xl, op["ya"] + m * (xl - a), color="#1f3a93", linewidth=1.6, label=f"{kind} line (slope {m:+.4g}/bar)")
        tch = [t for t in op["tch"] if lo <= t <= hi]
        if tch: ax.scatter(tch, [op["ya"] + m * (t - a) for t in tch], s=70, facecolors="none", edgecolors="#1f3a93", linewidths=1.6, label=f"{len(op['tch'])} touches")
        if lo <= t0 <= hi:
            ax.axvline(t0, color="black", linestyle=":", linewidth=1)
            ax.scatter([t0], [op["entry"]], marker="v" if d < 0 else "^", s=120, color="black", zorder=5, label=f"entry {op['entry']:.5g} ({'short' if d < 0 else 'long'})")
        ax.axhline(op["stop0"], color="#e67e22", linestyle="--", linewidth=1.2, label=f"initial stop {op['stop0']:.5g} ({op.get('stop_src', '')})")
        if abs(op.get("stop", op["stop0"]) - op["stop0"]) > 1e-12: ax.axhline(op["stop"], color="#e67e22", linewidth=1.2, label=f"current stop {op['stop']:.5g}")
        saf = op.get("saf")
        if saf:
            xs = np.arange(max(saf["a"], lo), hi + 1); ms = (saf["yb"] - saf["ya"]) / max(1, saf["b"] - saf["a"])
            ax.plot(xs, saf["ya"] + ms * (xs - saf["a"]), color="#e67e22", linestyle="-.", linewidth=1, label="stop anchor line")
        if P and P.get("fill"): ax.axhline(P["fill"], color="gray", linestyle=":", linewidth=1, label=f"actual fill {P['fill']:.5g}")
        if "exit_idx" in op and lo <= op["exit_idx"] <= hi: ax.scatter([op["exit_idx"]], [op["exit"]], marker="x", s=100, color="black", zorder=5, label=f"exit {op['exit']:.5g} ({op.get('why', '')})")
        ax.set_xlim(lo, hi); ticks = x[:: max(1, len(x) // 10)]
        ax.set_xticks(ticks); ax.set_xticklabels([datetime.fromtimestamp(int(T[i]), timezone.utc).strftime("%m-%d %H:%M") for i in ticks], rotation=30, fontsize=8)
        ax.legend(loc="best", fontsize=8); ax.grid(alpha=0.2)

    hi = n - 1; lo_full = max(0, a - 30); lo_zoom = max(lo_full, t0 - nb)
    draw(ax1, lo_full, hi, candles=False); draw(ax2, lo_zoom, hi, candles=True)
    ax1.set_title(f"{s}: {kind} line break, entry bar {datetime.fromtimestamp(int(T[t0]), timezone.utc):%Y-%m-%d %H:%M} UTC, R {op['R']:.5g}, "
                  f"span {t0 - a} bars (full line)"); ax2.set_title(f"last {hi - lo_zoom} bars")
    fig.tight_layout(); fig.savefig(out, dpi=120); plt.close(fig)


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    nb = int(args[args.index("--bars") + 1]) if "--bars" in args else 300
    syms = [a for a in args if not a.startswith("--") and not a.isdigit()]
    try: state = json.load(open(STATE_FILE))
    except Exception: state = {}
    for s in syms:
        T, trades, op = run_engine(s)
        T, O, H, L, C = load_series(cache_path(s))
        if op is None:
            if not trades: print(f"{s}: no open position and no trades"); continue
            op = trades[-1]; print(f"{s}: no open position; drawing the last closed trade")
        out = f"plot_{s}.png"; plot_trade(s, op, state.get("positions", {}).get(s), T, O, H, L, C, out, nb); print(f"{s} -> {out}")


if __name__ == "__main__":
    main()
