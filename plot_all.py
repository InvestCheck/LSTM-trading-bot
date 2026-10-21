#!/usr/bin/env python3
"""Keep a folder of charts for every trade the bot has taken. Reads trade_log.csv
(confirm and exit events), reruns the engine per symbol, and writes
plots/<SYMBOL>_<entry bar UTC>.png for each trade. A trade is redrawn once it closes
so the exit shows; otherwise existing files are left alone.

Run by hand or from cron on the droplet, offset from the bot's pass:
  35 * * * * cd ~/trendline-bot-repo && venv/bin/python plot_all.py >> plots/plot_all.log 2>&1
Copy the folder to the Mac with:
  rsync -av bot@<droplet>:~/trendline-bot-repo/plots/ ~/Desktop/bot_plots/
"""
import os, csv, json
from datetime import datetime, timezone
from live_ibkr import run_engine, cache_path, STATE_FILE, TRADE_LOG
from backtest_hull import load_series
from plot_position import plot_trade

OUT = "plots"


def main():
    os.makedirs(OUT, exist_ok=True)
    taken = {}                                       # (symbol, entry bar_time) -> closed?
    for r in csv.DictReader(open(TRADE_LOG)):
        if r["event"] == "confirm": taken[(r["symbol"], r["bar_time"])] = False
        elif r["event"] == "exit":
            for k in list(taken):
                if k[0] == r["symbol"] and not taken[k]: taken[k] = True
    try: state = json.load(open(STATE_FILE))
    except Exception: state = {}
    todo = {}
    for (s, bt), closed in taken.items():
        out = os.path.join(OUT, f"{s}_{bt.replace(' ', 'T').replace(':', '')}{'' if closed else '_open'}.png")
        if not os.path.exists(out): todo.setdefault(s, []).append((bt, closed, out))
    for s, items in todo.items():
        T, trades, op = run_engine(s); T, O, H, L, C = load_series(cache_path(s))
        for bt, closed, out in items:
            ts = int(datetime.strptime(bt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())
            tr = next((t for t in trades if abs(int(T[t["t0"]]) - ts) < 60), None)
            if tr is None and op is not None and abs(int(T[op["t0"]]) - ts) < 60: tr = op
            if tr is None: print(f"{s} {bt}: engine trade not found"); continue
            plot_trade(s, tr, state.get("positions", {}).get(s), T, O, H, L, C, out)
            stale = out.replace(".png", "_open.png") if closed else None
            if stale and os.path.exists(stale): os.remove(stale)
            print(f"{s} {bt} -> {out}")


if __name__ == "__main__":
    main()
