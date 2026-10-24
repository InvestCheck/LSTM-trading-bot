#!/usr/bin/env python3
"""Shadow of the 2 touch engine on the bot's own cached bars. Places no orders,
touches nothing the paper run uses. Scores every closed 2 touch engine trade at
engine prices, with the v2 gate (cheap instrument, frozen tier score >= cutoff),
the stop size in ATR and ADX(14) on the bar before entry, so the April decision on
two touch lines (and the stop rule and ADX subsets inside it) is made on trades
nothing was fitted to.

Forward integrity: the first run only sets a watermark at the last cached bar and
logs nothing; from then on a trade is logged once, when the engine has closed it,
if its exit is after the watermark. Trades still open are counted, not logged.

Files (repo folder):  shadow_touch2.csv (one row per closed trade),
shadow_touch2_state.json (watermarks), shadow_touch2.log (run summaries).
Cron (droplet), daily after the 21:05 UTC pass has finished:
  25 22 * * * cd ~/trendline-bot-repo && nice -n 10 venv/bin/python shadow_touch2.py >> shadow_touch2.log 2>&1
"""
import os, csv, json, math, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import load_series
from instruments import TICKS
from ib_contracts import UNIVERSE
from research_exits import harvest, exit_engine, features, rolling_extreme, WARMUP_DAYS
from tier import CLASSES, NAMES

MINTOUCH = 2; CACHE = "cache"; OUT_CSV = "shadow_touch2.csv"; STATE = "shadow_touch2_state.json"
COLS = ["logged_at", "symbol", "dir", "touches", "span", "entry_time", "exit_time", "entry", "stop0", "exit", "why", "R", "R_px",
        "stop_atr", "score", "v2", "adx", "cost_r"]


def wilder(x, n):
    out = np.zeros_like(x); out[n - 1] = x[:n].mean() if len(x) >= n else 0
    for i in range(n, len(x)): out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def adx14(H, L, C, n=14):
    up = np.diff(H, prepend=H[0]); dn = -np.diff(L, prepend=L[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(H - L, np.maximum(abs(H - np.roll(C, 1)), abs(L - np.roll(C, 1)))); tr[0] = H[0] - L[0]
    atr = wilder(tr, n); pdi = 100 * wilder(pdm, n) / np.maximum(atr, 1e-12); ndi = 100 * wilder(ndm, n) / np.maximum(atr, 1e-12)
    return wilder(100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12), n)


def iso(ts): return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M")


def main():
    t_start = time.time(); now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cfg = json.load(open("v2_config.json")); cheap = set(cfg["cheap"]); inst_cost = cfg["inst_cost"]
    m = json.load(open(os.path.join("research", "tier_model.json"))); assert m["names"] == NAMES
    mu, sd, lo, hi, w = (np.array(m[k]) for k in ("mu", "sd", "clip_lo", "clip_hi", "weights")); b, cut = m["intercept"], m["cutoff"]
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"started": now, "wm": {}}
    first = not state["wm"]
    new_rows = []; n_open = 0; held = []
    for s in UNIVERSE:
        path = os.path.join(CACHE, f"{s}.csv")
        if not os.path.exists(path): continue
        try:
            T, O, H, L, C = load_series(path)
        except Exception as e:
            print(f"{now} {s}: cache unreadable ({e})"); continue
        if len(T) < 5000: continue
        last_ts = int(T[-1])
        if first or s not in state["wm"]:
            state["wm"][s] = last_ts; continue                     # history is not forward data
        tick = TICKS.get(s, 0.0); start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(path, start_ts=start_ts, fill="intrabar", MINTOUCH=MINTOUCH)
        D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
        D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
        adx = adx14(D["H"], D["L"], D["C"]); n = len(D["T"])
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        busy, taken = -1, set(); newest = state["wm"][s]
        for t in sorted(by_bar):
            if t < busy: continue
            for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                if sg["edge"] in taken: continue
                taken.add(sg["edge"]); ei, ex, why, _ = exit_engine(D, sg); busy = ei
                is_open = (ei >= n - 1 and why == "eod")
                if is_open: n_open += 1; held.append(f"{s}{'+' if sg['dir'] > 0 else '-'}"); break
                xt = int(D["T"][ei])
                if xt <= state["wm"][s]: break
                R = abs(sg["entry"] - sg["stop0"]); cost = (2.0 * tick) / R if tick else 0.0
                r = (ex - sg["entry"]) / R * sg["dir"] - cost
                sg["ts"] = int(D["T"][t]); sg["span"] = t - sg["a"]; f = features(D, sg)
                dt = datetime.fromtimestamp(sg["ts"], timezone.utc); cls = next((c for c, l in CLASSES.items() if s in l), "OTHER")
                x = [f[k] for k in NAMES[:9]] + [math.log(max(1, sg["span"])), sg["touches"], 1.0 if sg["dir"] > 0 else 0.0, 1.0 if sg["stop_src"] == "ema" else 0.0,
                     math.sin(2 * math.pi * dt.hour / 24), math.cos(2 * math.pi * dt.hour / 24), 1.0 if dt.weekday() == 6 else 0.0, inst_cost.get(s, 0.1)] + [1.0 if cls == c else 0.0 for c in CLASSES]
                x = np.array(x, float); x[~np.isfinite(x)] = 0; z = np.clip((np.clip(x, lo, hi) - mu) / sd, -5, 5); sc = float(b + z @ w)
                p = max(1, t - 1); ap = D["A"][p] if D["A"][p] > 0 else float("nan")
                new_rows.append(dict(logged_at=now, symbol=s, dir=sg["dir"], touches=sg["touches"], span=sg["span"], entry_time=iso(sg["ts"]), exit_time=iso(xt),
                                     entry=round(sg["entry"], 6), stop0=round(sg["stop0"], 6), exit=round(ex, 6), why=why, R=round(r, 4), R_px=round(R, 6),
                                     stop_atr=round(R / ap, 2) if ap == ap else "", score=round(sc, 4), v2=int(s in cheap and sc >= cut), adx=round(float(adx[p]), 1), cost_r=round(cost, 4)))
                newest = max(newest, xt); break
        state["wm"][s] = max(state["wm"][s], last_ts)
    if new_rows:
        write_header = not os.path.exists(OUT_CSV)
        with open(OUT_CSV, "a", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=COLS); (wr.writeheader() if write_header else None); wr.writerows(new_rows)
    json.dump(state, open(STATE, "w"), indent=1)
    if first:
        print(f"{now} first run: watermarks set at the last cached bar for {len(state['wm'])} symbols, nothing logged"); return
    tot = sum(1 for _ in csv.DictReader(open(OUT_CSV))) if os.path.exists(OUT_CSV) else 0
    v2n = [r for r in new_rows if r["v2"]]
    print(f"{now} 2 touch shadow: {len(new_rows)} closed ({len(v2n)} v2, " + ", ".join(f"{r['symbol']} {r['R']:+.2f}" for r in v2n) + f") | open {n_open}: {' '.join(held)} | "
          f"logged so far {tot} | {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
