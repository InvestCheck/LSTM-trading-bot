#!/usr/bin/env python3
"""Live / paper runner for the trendline-walk strategy on Interactive Brokers.

Design
------
The backtest `run()` is a closed simulation that opens and closes its own
trades. Live we split that into two halves:

  * entry detection  -> reuse `run()` over the cached history; a fresh signal is
    a position that OPENS on the just-closed bar (read via return_open).
  * position manager -> `exit_step()`, one bar of the exit engine, which drives
    the real protective stop order and emits close signals. Verified to
    reproduce `exit_sim()` bar for bar.

Deep history
------------
The method uses trendlines anchored years back (a 4-year line with a recent
3rd touch). So the bot keeps the FULL multi-year 1H history per symbol, the
same depth the backtest had. On first run per symbol it backfills that history
from IBKR in chunks walking backward and caches it to disk; each hour it pulls
only the last few days and appends. MAXSPAN is raised to match.

Stages (set MODE): "shadow" (logs only, no orders) -> "paper" -> "live".

NOTE: paper fills are optimistic; paper P&L reads better than reality. Raising
MAXSPAN above 1200 changes the strategy vs the validated backtest numbers, so
re-backtest at the new span before trusting it. This is not financial advice.
"""
import os, json, math, csv, tempfile, sys
from datetime import datetime, timezone, timedelta

from backtest_hull import run, load_series, ema, atr, exit_sim   # noqa: F401


# --------------------------------------------------------------------------- #
# Trade logger: append-only, fsynced so a crash leaves a record, not a hole.
# This file is the source of truth for the paper-vs-backtest comparison.
# --------------------------------------------------------------------------- #

LOG_FILE = os.environ.get("TRADE_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_log.csv"))
_LOG_FIELDS = ["ts_utc", "event", "symbol", "mode", "dir", "qty",
               "entry", "stop", "R_planned", "fill", "exit_px", "R_realized", "note"]

def log_event(event, symbol, **f):
    """Append one row. event in {signal, entry, stop_move, exit, error}."""
    row = {k: "" for k in _LOG_FIELDS}
    row["ts_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row["event"] = event
    row["symbol"] = symbol
    row.update({k: v for k, v in f.items() if k in _LOG_FIELDS})
    new = not os.path.exists(LOG_FILE)
    try:
        with open(LOG_FILE, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=_LOG_FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception as e:                       # logging must never crash the bot
        print(f"[log] failed to write {event} for {symbol}: {e}")


# --------------------------------------------------------------------------- #
# Strategy core (no broker dependency, unit tested)
# --------------------------------------------------------------------------- #

def exit_step(st, h, l, c, e21, e200, atr_t):
    """Advance one open position by a single closed bar.

    `st` is a mutable dict: dir (+1/-1), entry, R (price risk), stop, phase.
    Returns (action, value): ("exit", price), ("modify_stop", newstop), or
    ("hold", None). Mirrors one iteration of `exit_sim` exactly.
    """
    d, entry, R = st["dir"], st["entry"], st["R"]
    stop_before = st["stop"]
    ex = None
    if d > 0:
        if h - e21 >= 3.5 * atr_t: ex = e21 + 3.5 * atr_t
        if ex is None and st["phase"] == 1:
            if l <= st["stop"]: ex = st["stop"]
            elif h >= entry + R: st["phase"] = 2; st["stop"] = entry
        if ex is None and st["phase"] == 2:
            if l <= entry: ex = entry
            elif c < e21: ex = c
        if ex is None and st["phase"] == 1 and e200 < c and e200 > st["stop"] \
                and abs(e200 - entry) >= 0.5 * R:
            st["stop"] = e200
    else:
        if e21 - l >= 3.5 * atr_t: ex = e21 - 3.5 * atr_t
        if ex is None and st["phase"] == 1:
            if h >= st["stop"]: ex = st["stop"]
            elif l <= entry - R: st["phase"] = 2; st["stop"] = entry
        if ex is None and st["phase"] == 2:
            if h >= entry: ex = entry
            elif c > e21: ex = c
        if ex is None and st["phase"] == 1 and e200 > c and e200 < st["stop"] \
                and abs(e200 - entry) >= 0.5 * R:
            st["stop"] = e200
    if ex is not None:
        return ("exit", float(ex))
    if st["stop"] != stop_before:
        return ("modify_stop", float(st["stop"]))
    return ("hold", None)


def detect_entry(name, T, O, H, L, C, start_ts, maxspan=1200):
    """Return a signal if a position OPENS on the last (just-closed) bar, else None.

    Runs the detector over the full cached series and reads the position open at
    the final bar (return_open). A signal whose entry bar is the last bar means
    the current candle just broke a qualifying trendline, so you enter now, on
    the break candle. `maxspan` is passed through so long (multi-year) lines are
    allowed. Returns dir, entry, stop (stop0), R, entry_ts.

    Timing: no extra lag. Touches confirm a couple of bars after they print (the
    pivot window, C+2) and the line is built from confirmed touches; entry is on
    the breaking candle. Reading the OPEN position (not run()'s closed list) is
    what makes that show up immediately.
    """
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time", "open", "high", "low", "close", "volume"])
            for i in range(len(T)):
                w.writerow([int(T[i]), O[i], H[i], L[i], C[i], 0])
        _, _, _, _, op = run(name, path, 1.0, start_ts, CAP=1e12,
                             MAXSPAN=maxspan, return_open=True)
    finally:
        os.remove(path)
    last = len(C) - 1
    if op is not None and op["t0"] == last:
        return dict(dir=op["dir"], entry=op["entry"], stop=op["stop0"],
                    R=abs(op["entry"] - op["stop0"]), phase=1,
                    entry_ts=int(T[last]))
    return None


def size_contracts(risk_dollars, stop_distance, multiplier):
    """Whole contracts so that a stop-out loses about risk_dollars."""
    per = stop_distance * multiplier
    return max(1, int(risk_dollars / per)) if per > 0 else 0


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

MODE = "shadow"                 # "shadow" -> "paper" -> "live"
HOST, CLIENT_ID = "127.0.0.1", 1
PORT = {"paper": 4002, "live": 4001}.get(MODE, 4002)   # IB Gateway paper=4002

RISK_DOLLARS = 200.0            # risk per trade
MAX_POSITIONS = 4               # hard cap on concurrent open trades
DAILY_LOSS_LIMIT = 600.0        # kill switch: stop opening if exceeded today
DELAYED_DATA = True             # True = delayed bars so the bot does not fight your live
                                # session for the one real-time data line (Error 162).

# Deep history: hold the full multi-year series so old anchors exist.
HISTORY_YEARS = 4               # how far back to backfill and cache
MAXSPAN = 1200                  # longest line in bars (~2.5 months). 18.5y backtest on all
                                # metals shows 1200 beats every longer span on profit factor;
                                # the strongest edge is in shorter structural lines, not multi
                                # year ones. At this span the bot needs only ~1200 + warmup bars
                                # of history, so the deep CSV seed is optional (a few months of
                                # IBKR history suffices).
SEED_DIR = "seed"               # drop your multi-year 1H CSVs here as seed/<symbol>.csv (the same
                                # files you backtested on). IBKR continuous futures cannot walk back
                                # (Error 10339) and have shallow intraday history, so seeding the deep
                                # history from CSV is how the bot matches the backtest's depth.
UPDATE_DURATION = "3 D"         # recent pull each hour to append new bars
HIST_TIMEOUT = 120              # seconds per historical request
CACHE_DIR = "cache"
STATE_FILE = "live_state.json"
WARMUP_BARS = 350               # >=200 for the 200 EMA plus margin

# name -> contract spec. Bars on the continuous series; orders on the front month.
SYMBOLS = {
    "MGC": dict(symbol="MGC", exchange="COMEX", currency="USD", multiplier=10),
    "PL":  dict(symbol="PL",  exchange="NYMEX", currency="USD", multiplier=50),
    "HG":  dict(symbol="HG",  exchange="COMEX", currency="USD", multiplier=25000),
    # add SI, PA; confirm multiplier and exchange in TWS Contract Details
}


# --------------------------------------------------------------------------- #
# IBKR wiring (guarded import so the file loads without ib_async)
# --------------------------------------------------------------------------- #

def main():
    try:
        from ib_async import IB, Future, ContFuture, MarketOrder, StopOrder, Contract
    except ImportError:
        print("ib_async not installed. Run:  pip install ib_async")
        return
    import numpy as np

    # ---- state -----------------------------------------------------------
    def load_state():
        if os.path.exists(STATE_FILE):
            s = json.load(open(STATE_FILE)); s.setdefault("seen", {}); return s
        return dict(positions={}, realized_today=0.0, day=None, seen={})

    def save_state(s):
        json.dump(s, open(STATE_FILE, "w"), indent=1)

    state = load_state()
    ib = IB()

    # ---- connection with auto reconnect ----------------------------------
    def apply_session():
        if DELAYED_DATA:
            ib.reqMarketDataType(3)   # delayed; coexists with your live session

    def ensure_connected():
        """Reconnect if the socket dropped (e.g. after the Gateway daily restart)."""
        if ib.isConnected():
            return True
        for attempt in range(5):
            try: ib.disconnect()
            except Exception: pass
            try:
                ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=20)
                apply_session()
                print("reconnected to IBKR")
                return True
            except Exception as e:
                print(f"reconnect attempt {attempt + 1} failed: {e}")
                ib.sleep(15)
        return False

    # ---- deep-history cache ---------------------------------------------
    def cache_path(name):
        return os.path.join(CACHE_DIR, f"{name}.csv")

    def write_cache(name, T, O, H, L, C):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path(name), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["time", "open", "high", "low", "close", "volume"])
            for i in range(len(T)):
                w.writerow([int(T[i]), O[i], H[i], L[i], C[i], 0])

    def merge_bars(arrays, bars):
        d = {}
        if arrays is not None:
            T, O, H, L, C = arrays
            for i in range(len(T)):
                d[int(T[i])] = (O[i], H[i], L[i], C[i])
        for b in bars:
            d[int(b.date.timestamp())] = (b.open, b.high, b.low, b.close)
        ks = sorted(d)
        return (np.array(ks),
                np.array([d[k][0] for k in ks], float),
                np.array([d[k][1] for k in ks], float),
                np.array([d[k][2] for k in ks], float),
                np.array([d[k][3] for k in ks], float))

    def hist(cont, end, duration):
        return ib.reqHistoricalData(cont, endDateTime=end, durationStr=duration,
                                    barSizeSetting="1 hour", whatToShow="TRADES",
                                    useRTH=False, keepUpToDate=False, timeout=HIST_TIMEOUT)

    def backfill(name, spec):
        cont = ContFuture(symbol=spec["symbol"], exchange=spec["exchange"],
                          currency=spec["currency"])
        seed = os.path.join(SEED_DIR, f"{name}.csv")
        if os.path.exists(seed):
            print(f"[{name}] seeding deep history from {seed}")
            arrays = load_series(seed)
            try:                                 # bring it up to now with recent IBKR bars
                bars = hist(cont, "", "30 D")    # endDateTime='' only; ContFuture forbids an end date
                if bars: arrays = merge_bars(arrays, bars)
            except Exception as e:
                print(f"[{name}] could not append recent IBKR bars: {e}")
            write_cache(name, *arrays)
            return load_series(cache_path(name))
        # No seed file: IBKR continuous intraday history is shallow and cannot be walked
        # back (Error 10339), so this gets only what a single request returns. For the
        # full multi-year depth the strategy needs, drop your CSV at seed/<symbol>.csv.
        print(f"[{name}] no seed/{name}.csv -> pulling only the limited continuous history IBKR allows")
        try:
            bars = hist(cont, "", f"{HISTORY_YEARS} Y")
        except Exception:
            bars = hist(cont, "", "1 Y")
        if not bars:
            return None
        write_cache(name, *merge_bars(None, bars))
        return load_series(cache_path(name))

    def update_cache(name, spec):
        cont = ContFuture(symbol=spec["symbol"], exchange=spec["exchange"],
                          currency=spec["currency"])
        arrays = load_series(cache_path(name))
        bars = hist(cont, "", UPDATE_DURATION)
        if bars:
            arrays = merge_bars(arrays, bars)
            write_cache(name, *arrays)
        return arrays

    def get_series(name, spec):
        if not os.path.exists(cache_path(name)):
            return backfill(name, spec)
        return update_cache(name, spec)

    # ---- order helpers (paper/live only) ---------------------------------
    def front_contract(spec, buffer_days=14):
        det = ib.reqContractDetails(Future(symbol=spec["symbol"], exchange=spec["exchange"],
                                           currency=spec["currency"]))
        today = datetime.now(timezone.utc).date()
        rows = []
        for d in det:
            ymd = d.contract.lastTradeDateOrContractMonth
            if len(ymd) == 6:
                ymd += "01"
            try:
                exp = datetime.strptime(ymd, "%Y%m%d").date()
            except ValueError:
                continue
            rows.append((exp, d.contract))
        rows.sort(key=lambda r: r[0])
        for exp, c in rows:                      # skip anything in/near its delivery window
            if (exp - today).days >= buffer_days:
                ib.qualifyContracts(c); return c
        c = rows[-1][1]; ib.qualifyContracts(c); return c

    def place_bracket(name, spec, sig):
        contract = front_contract(spec)
        qty = size_contracts(RISK_DOLLARS, abs(sig["entry"] - sig["stop"]), spec["multiplier"])
        action = "BUY" if sig["dir"] > 0 else "SELL"
        opp = "SELL" if sig["dir"] > 0 else "BUY"
        entry = MarketOrder(action, qty); entry.transmit = False
        entry.tif = "GTC"; entry.outsideRth = True
        et = ib.placeOrder(contract, entry)
        stop = StopOrder(opp, qty, sig["stop"]); stop.parentId = et.order.orderId
        stop.tif = "GTC"; stop.transmit = True
        stp = ib.placeOrder(contract, stop)
        # short wait to capture the actual fill price for the log
        fill = None
        for _ in range(15):
            ib.waitOnUpdate(timeout=2)
            if et.orderStatus.status == "Filled" and et.orderStatus.avgFillPrice:
                fill = float(et.orderStatus.avgFillPrice); break
            if et.orderStatus.status in ("Cancelled", "Inactive", "ApiCancelled"):
                break
        return dict(con_id=contract.conId, qty=qty, stop_order_id=stp.order.orderId,
                    entry=sig["entry"], stop=sig["stop"], R=sig["R"], dir=sig["dir"], phase=1,
                    fill=fill)

    def modify_stop(pos, newstop):
        for tr in ib.openTrades():
            if tr.order.orderId == pos.get("stop_order_id"):
                tr.order.auxPrice = round(newstop, 2); ib.placeOrder(tr.contract, tr.order); break

    def close_position(pos):
        opp = "SELL" if pos["dir"] > 0 else "BUY"
        for tr in ib.openTrades():
            if tr.order.orderId == pos.get("stop_order_id"):
                ib.cancelOrder(tr.order)
        c = Contract(conId=pos["con_id"]); ib.qualifyContracts(c)
        ib.placeOrder(c, MarketOrder(opp, pos["qty"]))

    # ---- per-bar logic ---------------------------------------------------
    def on_bar(name, spec):
        series = get_series(name, spec)
        if series is None:
            print(f"[{name}] no data"); return
        T, O, H, L, C = series
        if len(C) < WARMUP_BARS:
            return
        e21, e200, A = ema(C, 21), ema(C, 200), atr(H, L, C)
        last = len(C) - 1
        pos = state["positions"].get(name)

        if pos:                                  # manage the open trade
            act, val = exit_step(pos, H[last], L[last], C[last], e21[last], e200[last], A[last])
            if act == "exit":
                rr = ((val - pos["entry"]) / pos["R"]) * pos["dir"]
                print(f"[{name}] EXIT @ {val:.2f}  ~{rr:+.2f}R")
                if MODE != "shadow" or pos.get("live_managed"): close_position(pos)
                state["realized_today"] += rr * RISK_DOLLARS
                log_event("exit", name, mode=MODE, dir=pos["dir"], qty=pos.get("qty", ""),
                          entry=round(pos["entry"], 4), exit_px=round(val, 4), R_realized=round(rr, 3),
                          note=pos.get("why", ""))
                del state["positions"][name]
            elif act == "modify_stop":
                print(f"[{name}] move stop -> {val:.2f}")
                if MODE != "shadow" or pos.get("live_managed"): modify_stop(pos, val)
                log_event("stop_move", name, mode=MODE, dir=pos["dir"], stop=round(val, 4))
            save_state(state)
            return

        if len(state["positions"]) >= MAX_POSITIONS:
            return
        if state["realized_today"] <= -DAILY_LOSS_LIMIT:
            print("daily loss limit hit, not opening"); return
        start_ts = int(T.min()) + 60 * 86400
        sig = detect_entry(name, T, O, H, L, C, start_ts, MAXSPAN)
        if not sig:
            return
        if name not in state["seen"]:            # prime: never trade a stale signal at startup
            state["seen"][name] = sig["entry_ts"]; save_state(state); return
        if sig["entry_ts"] != state["seen"][name]:
            state["seen"][name] = sig["entry_ts"]
            side = "LONG" if sig["dir"] > 0 else "SHORT"
            print(f"[{name}] ENTRY {side} @ {sig['entry']:.2f} stop {sig['stop']:.2f} R={sig['R']:.2f}")
            log_event("signal", name, mode=MODE, dir=sig["dir"],
                      entry=round(sig["entry"], 4), stop=round(sig["stop"], 4), R_planned=round(sig["R"], 4))
            posrec = sig if MODE == "shadow" else place_bracket(name, spec, sig)
            state["positions"][name] = posrec
            if MODE != "shadow":
                log_event("entry", name, mode=MODE, dir=sig["dir"], qty=posrec.get("qty", ""),
                          entry=round(sig["entry"], 4), stop=round(sig["stop"], 4),
                          R_planned=round(sig["R"], 4),
                          fill=(round(posrec["fill"], 4) if posrec.get("fill") is not None else ""),
                          note=("filled" if posrec.get("fill") is not None else "working"))
            save_state(state)

    # ---- test-trade: place the most recent detector signal on paper ------
    def detector_trades(name, T, O, H, L, C, start_ts):
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                w = csv.writer(f); w.writerow(["time", "open", "high", "low", "close", "volume"])
                for i in range(len(T)):
                    w.writerow([int(T[i]), O[i], H[i], L[i], C[i], 0])
            _, trades, _, _ = run(name, path, 1.0, start_ts, CAP=1e12, MAXSPAN=MAXSPAN)
        finally:
            os.remove(path)
        return trades

    def run_test_trade():
        accts = ib.managedAccounts()
        if not any(a.startswith("DU") for a in accts):
            print(f"REFUSING test trade: account is not paper (DU...). accounts={accts}"); return
        best = None                              # (entry_ts, name, spec, trade)
        for name, spec in SYMBOLS.items():
            series = get_series(name, spec)
            if series is None:
                continue
            T, O, H, L, C = series
            trades = detector_trades(name, T, O, H, L, C, int(T.min()) + 60 * 86400)
            if not trades:
                print(f"[{name}] no detector signals in history"); continue
            tr = trades[-1]; ets = int(T[tr["t0"]]); Rp = abs(tr["entry"] - tr["stop0"])
            note = "" if Rp > 0 else "  (skipped: stop rounds to entry, R=0)"
            print(f"[{name}] most recent signal {datetime.fromtimestamp(ets, timezone.utc):%Y-%m-%d %H:%M}Z{note}")
            if Rp > 0 and (best is None or ets > best[0]):
                best = (ets, name, spec, tr, float(C[-1]), Rp)
        if best is None:
            print("no usable signal found across symbols"); return
        ets, name, spec, tr, last_close, Rp = best
        d = tr["dir"]; side = "LONG" if d > 0 else "SHORT"
        when = datetime.fromtimestamp(ets, timezone.utc)
        qty = max(1, size_contracts(RISK_DOLLARS, Rp, spec["multiplier"]))
        risk = qty * Rp * spec["multiplier"]
        print("\n=== TEST TRADE (paper) ===")
        print(f"picked {name} {side}  (latest usable signal, {when:%Y-%m-%d %H:%M}Z)")
        print(f"  backtest: entry {tr['entry']:.2f}  stop {tr['stop0']:.2f}  R(px) {Rp:.2f}")
        print(f"  sizing: {qty} contract(s), implied risk ~${risk:,.0f} at this stop")
        contract = front_contract(spec)
        action = "BUY" if d > 0 else "SELL"
        entry_order = MarketOrder(action, qty)
        entry_order.tif = "GTC"                   # survive until the reopen instead of dying as a DAY order
        entry_order.outsideRth = True
        et = ib.placeOrder(contract, entry_order)
        print(f"  placing {action} {qty} {name} ({contract.localSymbol}, exp {contract.lastTradeDateOrContractMonth}) market on {accts[0]} ...")
        fill = None; status = ""
        for _ in range(20):
            ib.waitOnUpdate(timeout=2)
            status = et.orderStatus.status
            if status == "Filled" and et.orderStatus.avgFillPrice:
                fill = float(et.orderStatus.avgFillPrice); break
            if status in ("Cancelled", "Inactive", "ApiCancelled"):
                break
        if fill is None and status in ("Cancelled", "Inactive", "ApiCancelled"):
            msg = "; ".join(l.message for l in et.log if l.message)
            print(f"  ORDER REJECTED ({status}): {msg}")
            print("  nothing recorded. fix and rerun --test-trade.")
            return
        ref = fill if fill is not None else float(last_close)
        stop_px = round(ref - d * Rp, 2)
        opp = "SELL" if d > 0 else "BUY"
        stop_order = StopOrder(opp, qty, stop_px); stop_order.tif = "GTC"
        stp = ib.placeOrder(contract, stop_order); ib.sleep(1)
        if fill is not None:
            print(f"  FILLED @ {fill:.2f}   protective stop @ {stop_px:.2f}")
        else:
            print(f"  working ({status}); will fill at the reopen. stop staged @ {stop_px:.2f} off last close {ref:.2f}")
        print(f"  -> same direction and R as the backtest; entry level differs (today's price, not the historical break)")
        state["positions"][name] = dict(con_id=contract.conId, qty=qty,
                                        stop_order_id=stp.order.orderId, entry=ref, stop=stop_px,
                                        R=Rp, dir=d, phase=1, live_managed=True)
        log_event("entry", name, mode="test-trade", dir=d, qty=qty,
                  entry=round(ref, 4), stop=round(stop_px, 4), R_planned=round(Rp, 4),
                  fill=(round(fill, 4) if fill is not None else ""),
                  note=("filled" if fill is not None else f"working ({status})"))
        state["seen"][name] = ets                # don't also open this as a fresh signal
        save_state(state)
        print("  recorded; the exit engine will manage it each bar. Check the Gateway.\n")

    # ---- run loop --------------------------------------------------------
    import time
    if not ensure_connected():
        print("could not connect; is the Gateway running on port %d?" % PORT); return
    print(f"connected in {MODE} mode on port {PORT}")
    if DELAYED_DATA:
        print("using delayed market data (set DELAYED_DATA=False for real-time)")
    if "--test-trade" in sys.argv:
        run_test_trade()
    print("running. Ctrl-C to stop.")
    try:
        while True:
            if not ensure_connected():
                time.sleep(60); continue
            now = datetime.now(timezone.utc)
            today = now.date().isoformat()
            if state.get("day") != today:
                state["day"] = today; state["realized_today"] = 0.0; save_state(state)
            for name, spec in SYMBOLS.items():
                try:
                    on_bar(name, spec)
                except Exception as e:
                    print(f"[{name}] error: {e}")
                    if not ib.isConnected():
                        ensure_connected()
            time.sleep(max(60, 3600 - (now.minute * 60 + now.second) + 5))
    except KeyboardInterrupt:
        print("stopped")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
