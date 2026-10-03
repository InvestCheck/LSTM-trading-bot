#!/usr/bin/env python3
"""Forward paper test runner for the trendline walk strategy on IBKR.

Implements forward_test_protocol.md. Read that first; this file follows it.

Design
------
Every hour, for each instrument in the frozen universe:

  1. DATA: append the just closed 1 hour bar from IBKR to a cached series that
     starts with the vendor history (FirstRateData, same files as the backtest).
     The vendor history is rescaled once at the splice so it sits in IBKR's
     price units, and the whole cache is rescaled by the new/old price ratio
     whenever the traded contract rolls. The engine ignores scale, so neither
     changes any decision. The cache is append only: a bar is never revised.

  2. ENGINE: rerun backtest_hull.run() over the full cached history at the
     frozen config (MINSPAN 2160, MAXSPAN 17520, intrabar, causal). Because the
     engine is prefix consistent and the cache is append only, every past
     decision is reproduced exactly on each rerun, so a trade keeps its
     identity (entry bar time + direction) from hour to hour.

  3. RECONCILE: mirror the engine's position at the broker.
       engine opened a trade on the bar that just closed -> market entry now,
                                                             protective stop at
                                                             the engine's stop
       engine moved its stop                               -> modify the stop
       engine closed the trade on that bar                 -> market exit now
       engine opened or closed while the bot was down      -> logged as MISSED,
                                                             never backfilled
     The engine decides at the bar close (its stop and trade acceptance use the
     closing bar's ATR, 200 EMA and pivots), so no live order can take the
     backtest's intrabar fill. The gap between engine price and actual fill is
     recorded on every trade; that gap is the execution cost the backtest
     could not see.

Rolls follow ib_contracts.roll_date(): the data series and the held position
roll together, in the same pass.

Scoring: trade_log.csv is the record. R_engine is the engine's gross R for the
trade (the scored number, costs applied in post), R_actual is from real fills.

Modes
-----
  shadow   full pipeline, logs every decision, places no orders. Run this on
           the Mac first.
  paper    orders on a DU (paper) account. Refuses anything else.
  There is no live mode.

Usage
-----
  python3 live_ibkr.py                      hourly loop in MODE
  python3 live_ibkr.py --once               one pass now, then exit
  python3 live_ibkr.py --symbols GC ES ZN   restrict the universe (testing only)
  python3 live_ibkr.py --replay 300 GC      offline: step the last 300 vendor
                                            bars one at a time through the full
                                            engine + reconcile logic, no IBKR,
                                            writes replay_trade_log.csv
Environment: DATA_DIR (vendor files folder, default ./seed), MODE (shadow|paper).
"""
import os, sys, csv, json, math, time, traceback, statistics as st
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import numpy as np

from backtest_hull import run, load_series
from batch_backtest import build_catalog, iso
from ib_contracts import IB as MAP, UNIVERSE, pick_active

# ----------------------------------------------------------------------------
# Config (frozen; see protocol)
# ----------------------------------------------------------------------------
MODE = os.environ.get("MODE", "shadow")          # shadow | paper
DATA_DIR = os.environ.get("DATA_DIR", "seed")    # FirstRateData files
HOST, PORT, CLIENT_ID = "127.0.0.1", 4002, 11
MINSPAN, MAXSPAN, WARMUP_DAYS = 2160, 17520, 60
QTY = 1                                          # contracts per trade; R accounting is per contract
RUN_MINUTE = 5                                   # minutes past the hour the pass starts
CACHE_DIR = "cache"
STATE_FILE = "live_state.json"
TRADE_LOG = "trade_log.csv"
EVENT_LOG = "events.log"
SPLICE_MIN_BARS, SPLICE_MAX_SPREAD = 10, 0.005   # vendor/IBKR overlap requirements
MAX_CATCHUP_DAYS = 120                           # longest gap the bot will try to fill from IBKR
FILL_WAIT_S = 20

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

LOG_FIELDS = ["ts_utc", "event", "symbol", "mode", "dir", "qty", "contract", "bar_time",
              "engine_px", "actual_px", "stop", "R_px", "R_engine", "R_actual", "why",
              "note", "order_id"]


class DataError(Exception):
    pass


# ----------------------------------------------------------------------------
# Logging. Append only, fsynced. trade_log.csv is the record of the test.
# ----------------------------------------------------------------------------
def log_event(msg):
    line = f"{datetime.now(UTC).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    try:
        with open(EVENT_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log_trade(event, symbol, **f):
    row = {k: "" for k in LOG_FIELDS}
    row.update(ts_utc=datetime.now(UTC).isoformat(timespec="seconds"), event=event,
               symbol=symbol, mode=MODE)
    for k, v in f.items():
        if k in LOG_FIELDS and v is not None:
            row[k] = f"{v:.10g}" if isinstance(v, float) else v
    new = not os.path.exists(TRADE_LOG)
    try:
        with open(TRADE_LOG, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
            fh.flush(); os.fsync(fh.fileno())
    except Exception as e:
        log_event(f"[log] FAILED to write {event} {symbol}: {e}")
    log_event(f"{event:12s} {symbol:5s} " + " ".join(f"{k}={row[k]}" for k in
              ("contract", "dir", "bar_time", "engine_px", "actual_px", "stop", "R_engine", "why", "note")
              if row[k] != ""))


# ----------------------------------------------------------------------------
# Time. Vendor files store US Eastern wall clock labelled as UTC; the engine
# only ever sees that convention, so IBKR bar times are converted into it.
# ----------------------------------------------------------------------------
def vendor_ts(dt_utc):
    return int(dt_utc.astimezone(ET).replace(tzinfo=UTC).timestamp())


def vendor_ts_to_utc(ts):
    return datetime.fromtimestamp(int(ts), UTC).replace(tzinfo=ET).astimezone(UTC)


def bar_complete(b, now_utc):
    return b.date + timedelta(hours=1) <= now_utc


# ----------------------------------------------------------------------------
# Cache files
# ----------------------------------------------------------------------------
def cache_path(s): return os.path.join(CACHE_DIR, f"{s}.csv")
def meta_path(s): return os.path.join(CACHE_DIR, f"{s}.json")


def read_meta(s):
    try:
        return json.load(open(meta_path(s)))
    except Exception:
        return {}


def write_meta(s, m):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = meta_path(s) + ".tmp"
    json.dump(m, open(tmp, "w"), indent=1)
    os.replace(tmp, meta_path(s))


def write_cache(s, rows):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = cache_path(s) + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([int(r[0]), f"{r[1]:.10g}", f"{r[2]:.10g}", f"{r[3]:.10g}", f"{r[4]:.10g}", 0])
    os.replace(tmp, cache_path(s))


def append_cache(s, rows):
    with open(cache_path(s), "a", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow([int(r[0]), f"{r[1]:.10g}", f"{r[2]:.10g}", f"{r[3]:.10g}", f"{r[4]:.10g}", 0])
        f.flush(); os.fsync(f.fileno())


def last_cache_bar(s):
    """(ts, close) of the last cached bar."""
    with open(cache_path(s), "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read().decode().strip().splitlines()
    r = tail[-1].split(",")
    return int(float(r[0])), float(r[4])


def rescale_cache(s, ratio):
    T, O, H, L, C = load_series(cache_path(s))
    write_cache(s, zip(T.tolist(), (O * ratio).tolist(), (H * ratio).tolist(),
                       (L * ratio).tolist(), (C * ratio).tolist()))


# ----------------------------------------------------------------------------
# Broker (ib_async). None when offline.
# ----------------------------------------------------------------------------
class Broker:
    def __init__(self):
        from ib_async import IB
        self.ib = IB()
        self.ib.RequestTimeout = 60
        self.ib.errorEvent += self._on_error
        self._resolved = {}          # sym -> (ContractDetails, roll_date, et_date)
        self.account = None

    def _on_error(self, reqId, code, msg, contract=None):
        if code in (2104, 2106, 2107, 2108, 2158, 2119, 2100, 10349, 202, 399):
            return                   # farm status, order echo, TIF default: noise
        log_event(f"[ib] error {code} req {reqId}: {msg}")

    def connect(self):
        if self.ib.isConnected():
            return True
        for attempt in range(6):
            try:
                try: self.ib.disconnect()
                except Exception: pass
                self.ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=30)
                self.ib.reqMarketDataType(3)      # delayed is fine; bars come from historical requests
                accts = self.ib.managedAccounts()
                self.account = accts[0] if accts else None
                if MODE == "paper" and not (self.account or "").startswith("DU"):
                    log_event(f"REFUSING paper mode: account {accts} is not a DU paper account")
                    self.ib.disconnect()
                    sys.exit(2)
                log_event(f"connected to IBKR {accts} on {PORT} ({MODE})")
                self._resolved.clear()
                return True
            except SystemExit:
                raise
            except Exception as e:
                log_event(f"connect attempt {attempt + 1} failed: {e}")
                time.sleep(20)
        return False

    def resolve(self, s, et_today):
        """Active contract for s under the protocol roll rule, cached per day."""
        hit = self._resolved.get(s)
        if hit and hit[2] == et_today:
            return hit[0], hit[1]
        from ib_async import Future
        spec = MAP[s]
        q = Future(symbol=spec["symbol"], exchange=spec["exchange"], currency=spec["currency"])
        if spec["tradingClass"]:
            q.tradingClass = spec["tradingClass"]
        det = self.ib.reqContractDetails(q)
        if not det:
            raise DataError("contract unresolved (check ib_contracts.py)")
        d, rd = pick_active(det, spec, et_today)
        if d is None:
            raise DataError("no traded month ahead of its roll date")
        self._resolved[s] = (d, rd, et_today)
        return d, rd

    def bars(self, contract, end, duration):
        b = self.ib.reqHistoricalData(contract, end, duration, "1 hour", "TRADES",
                                      useRTH=False, formatDate=2, keepUpToDate=False, timeout=90)
        self.ib.sleep(0.6)
        return list(b or [])

    def bars_back_to(self, contract, until_utc, now_utc):
        """1 hour bars from until_utc to now, walking back in 30 day chunks."""
        out, end = {}, now_utc
        for _ in range(max(1, MAX_CATCHUP_DAYS // 30)):
            bs = self.bars(contract, end, "30 D")
            if not bs:
                break
            for b in bs:
                out[b.date] = b
            first = min(b.date for b in bs)
            if first <= until_utc:
                break
            end = first
        return [out[k] for k in sorted(out)]

    def contract_by_conid(self, conid):
        from ib_async import Future
        c = Future(conId=conid)
        self.ib.qualifyContracts(c)
        return c

    # ---- orders -----------------------------------------------------------
    def position_qty(self, conid):
        for p in self.ib.positions():
            if p.contract.conId == conid:
                return int(p.position)
        return 0

    def open_trade(self, order_id):
        for t in self.ib.openTrades():
            if t.order.orderId == order_id:
                return t
        return None

    def fill_of(self, order_id):
        for t in self.ib.trades():
            if t.order.orderId == order_id and t.orderStatus.status == "Filled" and t.orderStatus.avgFillPrice:
                return float(t.orderStatus.avgFillPrice)
        return None

    def wait_fill(self, trade, seconds):
        for _ in range(seconds):
            self.ib.sleep(1)
            if trade.orderStatus.status == "Filled" and trade.orderStatus.avgFillPrice:
                return float(trade.orderStatus.avgFillPrice)
            if trade.orderStatus.status in ("Cancelled", "ApiCancelled", "Inactive"):
                return None
        return None

    def place_entry(self, contract, d, qty, stop_px):
        from ib_async import MarketOrder, StopOrder
        action, opp = ("BUY", "SELL") if d > 0 else ("SELL", "BUY")
        e = MarketOrder(action, qty); e.tif = "GTC"; e.outsideRth = True; e.transmit = False
        et = self.ib.placeOrder(contract, e)
        so = StopOrder(opp, qty, stop_px); so.tif = "GTC"; so.outsideRth = True
        so.parentId = et.order.orderId; so.transmit = True
        stt = self.ib.placeOrder(contract, so)
        fill = self.wait_fill(et, FILL_WAIT_S)
        return et.order.orderId, stt.order.orderId, fill, et.orderStatus.status

    def place_stop(self, contract, d, qty, stop_px):
        from ib_async import StopOrder
        opp = "SELL" if d > 0 else "BUY"
        so = StopOrder(opp, qty, stop_px); so.tif = "GTC"; so.outsideRth = True
        return self.ib.placeOrder(contract, so).order.orderId

    def modify_stop(self, contract, order_id, d, qty, stop_px):
        t = self.open_trade(order_id)
        if t is None:
            return self.place_stop(contract, d, qty, stop_px), "stop re-placed (old order not found)"
        t.order.auxPrice = stop_px
        self.ib.placeOrder(t.contract, t.order)
        return order_id, ""

    def cancel(self, order_id):
        t = self.open_trade(order_id)
        if t is not None:
            self.ib.cancelOrder(t.order)
            self.ib.sleep(1)

    def close(self, contract):
        """Flatten whatever the broker actually holds in this contract."""
        from ib_async import MarketOrder
        q = self.position_qty(contract.conId)
        if q == 0:
            return None, None
        o = MarketOrder("SELL" if q > 0 else "BUY", abs(q)); o.tif = "GTC"; o.outsideRth = True
        t = self.ib.placeOrder(contract, o)
        return self.wait_fill(t, FILL_WAIT_S), t.order.orderId


def round_stop(px, tick, d):
    """Round to the tick AWAY from the entry, so the broker stop can only fire
    when the engine's stop would have fired too."""
    if not tick:
        return px
    k = px / tick
    k = math.floor(k + 1e-9) if d > 0 else math.ceil(k - 1e-9)
    return round(k * tick, 10)


def stop_tick(s, details):
    return MAP[s].get("tick") or (details.minTick if details else 0)


# ----------------------------------------------------------------------------
# Data layer
# ----------------------------------------------------------------------------
def build_cache(s, broker, catalog, now_utc, et_today):
    """First run for a symbol: vendor history spliced to the active contract."""
    if s not in catalog:
        raise DataError(f"no vendor file in {DATA_DIR}")
    T, O, H, L, C = load_series(catalog[s])
    if broker is None:
        write_cache(s, zip(T.tolist(), O.tolist(), H.tolist(), L.tolist(), C.tolist()))
        write_meta(s, dict(conId=None, local="vendor", splice=None))
        return
    d, rd = broker.resolve(s, et_today)
    c = d.contract
    seed_end = vendor_ts_to_utc(int(T[-1]))
    bars = [b for b in broker.bars_back_to(c, seed_end - timedelta(days=5), now_utc)
            if bar_complete(b, now_utc)]
    if not bars:
        raise DataError("no IBKR bars for active contract")
    vend = {int(t): float(cl) for t, cl in zip(T.tolist(), C.tolist())}
    matched = [(vendor_ts(b.date), b.close) for b in bars if vendor_ts(b.date) in vend]
    if len(matched) < SPLICE_MIN_BARS:
        raise DataError(f"splice: only {len(matched)} bars overlap the vendor file; "
                        f"vendor ends {iso(int(T[-1]))}, IBKR bars start {bars[0].date:%Y-%m-%d}")
    ratios = [cl / vend[t] for t, cl in matched[-48:] if vend[t]]
    med = st.median(ratios)
    spread = max(abs(r / med - 1) for r in ratios)
    if spread > SPLICE_MAX_SPREAD:
        raise DataError(f"splice unstable: ratio spread {spread:.2%} (wrong contract or misaligned times)")
    first_ib = vendor_ts(bars[0].date)
    rows = [(int(T[i]), O[i] * med, H[i] * med, L[i] * med, C[i] * med)
            for i in range(len(T)) if int(T[i]) < first_ib]
    seen = set()
    for b in bars:
        t = vendor_ts(b.date)
        if t not in seen:
            seen.add(t); rows.append((t, b.open, b.high, b.low, b.close))
    rows.sort(key=lambda r: r[0])
    write_cache(s, rows)
    write_meta(s, dict(conId=c.conId, local=c.localSymbol, roll_date=rd.isoformat(),
                       splice=dict(at=iso(first_ib), ratio=med, spread=spread, overlap=len(matched)),
                       rolls=[]))
    log_trade("data_splice", s, contract=c.localSymbol, bar_time=iso(first_ib),
              note=f"vendor x{med:.6g}, {len(matched)} overlap bars, spread {spread:.3%}")


def update_cache(s, broker, now_utc, et_today):
    """Append new complete bars. Returns number appended."""
    meta = read_meta(s)
    last_ts, last_close = last_cache_bar(s)
    if broker is None:
        return 0
    d, rd = broker.resolve(s, et_today)
    c = d.contract
    if meta.get("conId") not in (None, c.conId):
        # the traded contract rolled: rescale the whole history by new/old
        old = broker.contract_by_conid(meta["conId"])
        ob = {vendor_ts(b.date): b.close for b in broker.bars(old, "", "5 D")}
        nb = broker.bars(c, "", "5 D")
        pairs = [(b.close, ob[vendor_ts(b.date)]) for b in nb if vendor_ts(b.date) in ob and ob[vendor_ts(b.date)]]
        if len(pairs) >= 6:
            ratio = st.median(n / o for n, o in pairs[-24:])
            how = f"{len(pairs)} overlap bars"
        elif nb:
            ratio = nb[-1].close / last_close
            how = "last close only (old contract had no bars)"
        else:
            raise DataError("roll: no bars for the new contract yet")
        rescale_cache(s, ratio)
        meta.setdefault("rolls", []).append(dict(date=et_today.isoformat(), frm=meta.get("local"),
                                                 to=c.localSymbol, ratio=ratio))
        meta.update(conId=c.conId, local=c.localSymbol, roll_date=rd.isoformat())
        write_meta(s, meta)
        log_trade("data_roll", s, contract=c.localSymbol,
                  note=f"{meta['rolls'][-1]['frm']} -> {c.localSymbol} x{ratio:.6g} ({how})")
        last_ts, last_close = last_cache_bar(s)
    gap_h = (now_utc - vendor_ts_to_utc(last_ts)).total_seconds() / 3600
    if gap_h > 24 * MAX_CATCHUP_DAYS:
        raise DataError(f"cache {gap_h / 24:.0f} days old; delete {cache_path(s)} to rebuild")
    if gap_h <= 60:
        bars = broker.bars(c, "", "3 D")
    else:
        bars = broker.bars_back_to(c, vendor_ts_to_utc(last_ts), now_utc)
    new = [(vendor_ts(b.date), b.open, b.high, b.low, b.close) for b in bars
           if bar_complete(b, now_utc) and vendor_ts(b.date) > last_ts]
    new.sort(key=lambda r: r[0])
    if new:
        append_cache(s, new)
    if meta.get("roll_date") != rd.isoformat():
        meta["roll_date"] = rd.isoformat(); write_meta(s, meta)
    return len(new)


def run_engine(s):
    T = load_series(cache_path(s))[0]
    _, trades, _, _, op = run(s, cache_path(s), 1.0, int(T.min()) + WARMUP_DAYS * 86400,
                              CAP=1e12, MINSPAN=MINSPAN, MAXSPAN=MAXSPAN,
                              fill="intrabar", causal=True, return_open=True)
    return T, trades, op


# ----------------------------------------------------------------------------
# Reconcile the engine's view with the broker's
# ----------------------------------------------------------------------------
def r_actual(P, exit_px):
    if P.get("fill") is None or exit_px is None or not P["R"]:
        return None
    return (exit_px - P["fill"]) / P["R"] * P["dir"]


def reconcile(s, T, trades, op, state, broker, details, now_utc):
    last = len(T) - 1
    last_ts = int(T[last])
    last_done = state["last_bar"].get(s)
    positions = state["positions"]
    P = positions.get(s)
    c = details.contract if details else None
    local = c.localSymbol if c else "shadow"
    tick = stop_tick(s, details)
    closed = {(int(T[x["t0"]]), x["dir"]): x for x in trades}
    paper = MODE == "paper" and broker is not None

    # ---- 0. pick up fills still pending from an earlier pass -------------
    if P and paper and P.get("fill") is None and P.get("entry_order_id"):
        fill = broker.fill_of(P["entry_order_id"])
        if fill is None and broker.position_qty(P["con_id"]) != 0:
            for p in broker.ib.positions():
                if p.contract.conId == P["con_id"]:
                    fill = p.avgCost / float(c.multiplier or 1) if c and c.multiplier else None
        if fill is not None:
            P["fill"] = fill
            log_trade("entry_fill", s, contract=P["local"], dir=P["dir"], qty=P["qty"],
                      bar_time=iso(P["entry_ts"]), engine_px=P["entry"], actual_px=fill,
                      order_id=P["entry_order_id"], note="late fill")

    # ---- 1. manage the held trade ----------------------------------------
    if P:
        key = (P["entry_ts"], P["dir"])
        tr = closed.get(key)
        is_open = op is not None and int(T[op["t0"]]) == P["entry_ts"] and op["dir"] == P["dir"]
        if is_open:
            # contract roll: data series already rescaled, engine stop is in new units
            if paper and c and P["con_id"] != c.conId:
                broker.cancel(P["stop_order_id"])
                old = broker.contract_by_conid(P["con_id"])
                fx, oid = broker.close(old)
                log_trade("roll_close", s, contract=P["local"], dir=P["dir"], qty=P["qty"],
                          bar_time=iso(last_ts), actual_px=fx, order_id=oid)
                spx = round_stop(op["stop"], tick, P["dir"])
                eid, sid, fill, status = broker.place_entry(c, P["dir"], P["qty"], spx)
                P.update(con_id=c.conId, local=c.localSymbol, entry_order_id=eid,
                         stop_order_id=sid, fill=fill, broker_closed=None, stop=op["stop"])
                P.setdefault("rolls", []).append(dict(at=iso(last_ts), close=fx, open=fill))
                log_trade("roll_open", s, contract=c.localSymbol, dir=P["dir"], qty=P["qty"],
                          bar_time=iso(last_ts), actual_px=fill, stop=spx, order_id=eid,
                          note="" if fill is not None else f"working ({status})")
                local = c.localSymbol
            # stop or phase moved
            if abs(op["stop"] - P["stop"]) > 1e-12 or op["phase"] != P.get("phase"):
                note = ""
                if paper and P.get("broker_closed") is None:
                    spx = round_stop(op["stop"], tick, P["dir"])
                    P["stop_order_id"], note = broker.modify_stop(c, P["stop_order_id"], P["dir"], P["qty"], spx)
                P["stop"], P["phase"] = op["stop"], op["phase"]
                log_trade("stop_move", s, contract=local, dir=P["dir"], bar_time=iso(last_ts),
                          stop=op["stop"], note=(f"phase {op['phase']} " + note).strip())
            # broker already flat (its stop fired) while the engine still holds
            if paper and P.get("broker_closed") is None and P.get("fill") is not None \
                    and broker.position_qty(P["con_id"]) == 0 and broker.open_trade(P["stop_order_id"]) is None:
                fx = broker.fill_of(P["stop_order_id"])
                P["broker_closed"] = fx if fx is not None else -1
                log_trade("broker_stop_filled", s, contract=local, dir=P["dir"], actual_px=fx,
                          bar_time=iso(last_ts), note="engine still open; trade stays scored on engine exit")
        elif tr is not None:
            exit_ts = int(T[tr["exit_idx"]])
            late = tr["exit_idx"] < last
            actual, oid, note = None, None, ("late exit, engine closed " + iso(exit_ts)) if late else ""
            if paper:
                if P.get("broker_closed") is not None:
                    actual = P["broker_closed"] if P["broker_closed"] != -1 else None
                    note = (note + " filled earlier by broker stop").strip()
                else:
                    broker.cancel(P["stop_order_id"])
                    actual, oid = broker.close(broker.contract_by_conid(P["con_id"]))
                    if actual is None and oid is None:
                        actual = broker.fill_of(P["stop_order_id"])
                        note = (note + " already flat, stop fill used").strip()
            log_trade("exit", s, contract=P["local"], dir=P["dir"], qty=P["qty"], bar_time=iso(exit_ts),
                      engine_px=tr["exit"], actual_px=actual, R_px=P["R"], R_engine=tr["R"],
                      R_actual=r_actual(P, actual), why=tr["why"], note=note, order_id=oid)
            del positions[s]
            P = None
        else:
            if not P.get("orphan_logged"):
                P["orphan_logged"] = True
                log_trade("error", s, contract=P["local"], bar_time=iso(P["entry_ts"]),
                          note="held trade not found in engine output; manual check needed")

    # ---- 2. entries ---------------------------------------------------------
    if s not in positions and op is not None:
        t0ts = int(T[op["t0"]])
        if op["t0"] == last:
            spx = round_stop(op["stop0"], tick, op["dir"])
            P = dict(entry_ts=t0ts, dir=op["dir"], entry=op["entry"], stop0=op["stop0"],
                     stop=op["stop"], R=op["R"], phase=op["phase"], qty=QTY,
                     con_id=c.conId if c else None, local=local, fill=None,
                     entry_order_id=None, stop_order_id=None, broker_closed=None,
                     opened=datetime.now(UTC).isoformat(timespec="seconds"))
            why = f"{op['kind']} line; {len(op['tch'])} touches; span {op['t0'] - op['a']} bars; stop {op['stop_src']}"
            log_trade("signal", s, contract=local, dir=op["dir"], qty=QTY, bar_time=iso(t0ts),
                      engine_px=op["entry"], stop=op["stop0"], R_px=op["R"], why=why)
            if paper:
                eid, sid, fill, status = broker.place_entry(c, op["dir"], QTY, spx)
                P.update(entry_order_id=eid, stop_order_id=sid, fill=fill)
                log_trade("entry_fill" if fill is not None else "entry_working", s, contract=local,
                          dir=op["dir"], qty=QTY, bar_time=iso(t0ts), engine_px=op["entry"],
                          actual_px=fill, stop=spx, order_id=eid,
                          note="" if fill is not None else f"status {status}")
            positions[s] = P
        elif t0ts not in state["missed"] and (last_done is None or t0ts > last_done):
            state["missed"].append(t0ts)
            log_trade("missed", s, contract=local, dir=op["dir"], bar_time=iso(t0ts),
                      engine_px=op["entry"], R_px=op["R"],
                      note="opened while bot was not running; not backfilled" if last_done else "open at bot start")

    # ---- 3. trades that opened and closed entirely while the bot was down ---
    for (t0ts, d), x in closed.items():
        if last_done is not None and t0ts > last_done and t0ts not in state["missed"] \
                and not (P and P["entry_ts"] == t0ts):
            state["missed"].append(t0ts)
            log_trade("missed", s, contract=local, dir=d, bar_time=iso(t0ts), engine_px=x["entry"],
                      R_px=abs(x["entry"] - x["stop0"]), R_engine=x["R"], why=x["why"],
                      note="opened and closed while bot was not running; not backfilled")

    state["last_bar"][s] = last_ts


# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        s = json.load(open(STATE_FILE))
    else:
        s = dict(mode=MODE, positions={}, last_bar={}, missed=[], excluded={},
                 started=datetime.now(UTC).isoformat(timespec="seconds"))
    if s.get("mode") != MODE:
        if s["positions"]:
            sys.exit(f"state file was written in {s.get('mode')} mode with open positions; "
                     f"move {STATE_FILE} aside before switching to {MODE}")
        s["mode"] = MODE
    return s


def save_state(s):
    tmp = STATE_FILE + ".tmp"
    json.dump(s, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE_FILE)


# ----------------------------------------------------------------------------
# One pass
# ----------------------------------------------------------------------------
def run_pass(broker, state, catalog, syms):
    now_utc = datetime.now(UTC)
    et_today = now_utc.astimezone(ET).date()
    if broker is not None:
        try:
            broker.ib.reqAllOpenOrders(); broker.ib.sleep(1)
        except Exception as e:
            log_event(f"reqAllOpenOrders failed: {e}")
    t_start = time.time()
    for s in syms:
        if broker is not None and not broker.ib.isConnected():
            log_event("connection lost mid pass; rest of the pass skipped"); break
        try:
            details = None
            if broker is not None:
                details, _ = broker.resolve(s, et_today)
            if not os.path.exists(cache_path(s)):
                build_cache(s, broker, catalog, now_utc, et_today)
                new = 1
            else:
                new = update_cache(s, broker, now_utc, et_today)
            if state["excluded"].pop(s, None):
                log_trade("included", s, note="data ok again")
            if new == 0 and broker is not None and s not in state["positions"]:
                continue                        # nothing new, nothing held
            T, trades, op = run_engine(s)
            reconcile(s, T, trades, op, state, broker, details, now_utc)
        except DataError as e:
            if state["excluded"].get(s) != str(e):
                state["excluded"][s] = str(e)
                log_trade("excluded", s, note=str(e))
        except Exception as e:
            log_event(f"[{s}] ERROR {e}\n{traceback.format_exc()}")
        finally:
            save_state(state)
    held = ", ".join(f"{k}{'+' if v['dir'] > 0 else '-'}" for k, v in state["positions"].items())
    log_event(f"pass done in {time.time() - t_start:.0f}s | held {len(state['positions'])}: {held or 'none'} "
              f"| excluded {len(state['excluded'])}")


def next_run(now):
    base = now.replace(minute=RUN_MINUTE, second=0, microsecond=0)
    return base if base > now else base + timedelta(hours=1)


def main():
    args = sys.argv[1:]
    syms = list(UNIVERSE)
    if "--symbols" in args:
        i = args.index("--symbols")
        syms = [a for a in args[i + 1:] if not a.startswith("--")]
    if MODE not in ("shadow", "paper"):
        sys.exit(f"MODE must be shadow or paper, got {MODE!r}; there is no live mode")
    catalog = build_catalog(DATA_DIR)

    if "--replay" in args:
        return replay(int(args[args.index("--replay") + 1]), args[args.index("--replay") + 2], catalog)

    state = load_state()
    broker = Broker()
    if not broker.connect():
        sys.exit("could not connect to IBKR Gateway")
    log_event(f"forward test runner: {MODE} mode, {len(syms)} symbols, data from {DATA_DIR}")
    if "--once" in args:
        run_pass(broker, state, catalog, syms)
        broker.ib.disconnect()
        return
    try:
        while True:
            nxt = next_run(datetime.now(UTC))
            wait = (nxt - datetime.now(UTC)).total_seconds()
            log_event(f"next pass at {nxt.astimezone(ET):%H:%M %Z} ({wait / 60:.0f} min)")
            while (nxt - datetime.now(UTC)).total_seconds() > 0:
                time.sleep(min(30, max(1, (nxt - datetime.now(UTC)).total_seconds())))
            if not broker.connect():
                log_event("no connection; pass skipped")
                continue
            run_pass(broker, state, catalog, syms)
    except KeyboardInterrupt:
        log_event("stopped by user")
    finally:
        try: broker.ib.disconnect()
        except Exception: pass


# ----------------------------------------------------------------------------
# Offline replay: exercise the engine + reconcile logic on vendor data only
# ----------------------------------------------------------------------------
def replay(n, s, catalog):
    global MODE, STATE_FILE, TRADE_LOG, EVENT_LOG, CACHE_DIR
    MODE, STATE_FILE, TRADE_LOG, EVENT_LOG, CACHE_DIR = ("shadow", "replay_state.json",
                                                         "replay_trade_log.csv", "replay_events.log", "replay_cache")
    for f in (STATE_FILE, TRADE_LOG, EVENT_LOG):
        if os.path.exists(f): os.remove(f)
    T, O, H, L, C = load_series(catalog[s])
    state = load_state()
    rows = list(zip(T.tolist(), O.tolist(), H.tolist(), L.tolist(), C.tolist()))
    log_event(f"replay {s}: stepping the last {n} bars one at a time")
    write_cache(s, rows[:len(rows) - n])
    for k in range(n, 0, -1):
        append_cache(s, [rows[len(rows) - k]])
        Tc, trades, op = run_engine(s)
        reconcile(s, Tc, trades, op, state, None, None, datetime.now(UTC))
        save_state(state)
    print(f"\nreplay done -> {TRADE_LOG}")
    if os.path.exists(TRADE_LOG):
        for r in csv.DictReader(open(TRADE_LOG)):
            print(f"  {r['event']:10s} {r['bar_time']:16s} dir {r['dir']:>2s} engine {r['engine_px']:>10s} "
                  f"stop {r['stop']:>10s} R {r['R_engine']:>7s} {r['why']} {r['note']}")


if __name__ == "__main__":
    main()
