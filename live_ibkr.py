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

Execution (EXEC)
----------------
  resting  at each close, for every line that already passes the engine's refit
           geometry and has a valid stop on data through that bar, rest a stop
           order at the level the next bar would have to touch (one per
           direction, OCA). A fill is at the line. At the next close the engine
           runs: if it produced that signal the fill is CONFIRMED and the stop
           becomes the engine's; if not, the position is SCRATCHED at market.
           Unfilled orders are cancelled and re-placed at the new levels. This
           is the only execution that keeps the backtest's edge (research).
  market   legacy: market order after the engine signals at the close.

Modes
-----
  shadow   full pipeline, logs every decision, places no orders. Run this on
           the Mac first. In resting execution, fills are simulated against the
           bar that closed.
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
import os, sys, csv, json, math, time, traceback, subprocess, statistics as st
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import numpy as np

from backtest_hull import run, load_series
from batch_backtest import build_catalog, iso
from ib_contracts import IB as MAP, UNIVERSE, pick_active, contract_rows
from entry_scan import scan, taken_edges, next_bar_orders
TIER = None                                      # protocol v2 gate, loaded in main()

# ----------------------------------------------------------------------------
# Config (frozen; see protocol)
# ----------------------------------------------------------------------------
MODE = os.environ.get("MODE", "shadow")          # shadow | paper
PROTOCOL = os.environ.get("PROTOCOL", "v2")      # v1: execute every signal. v2: tier cut + cost cap. v3: v2 + stop
                                                 # within 2.5 ATR (protocol_v2.md). Every engine signal is logged
                                                 # with its gate result, so v1 and v2 are scored from the same run.
EXEC = os.environ.get("EXEC", "resting")         # resting: stop orders at the line, confirmed or scratched at the
                                                 # close (fills at the line like the backtest). market: enter at the
                                                 # next open after the engine signals (loses ~0.07R/trade, research)
DATA_DIR = os.environ.get("DATA_DIR", "seed")    # FirstRateData files
HOST, PORT, CLIENT_ID = "127.0.0.1", 4002, 11
MINSPAN, MAXSPAN, WARMUP_DAYS = 2160, 17520, 60
QTY = 1                                          # contracts per trade; R accounting is per contract
RUN_MINUTE = 5                                   # minutes past the hour the pass starts
CACHE_DIR = "cache"
STATE_FILE = "live_state.json"
TRADE_LOG = "trade_log.csv"
EVENT_LOG = "events.log"
SPLICE_MIN_BARS, SPLICE_MAX_OFF = 10, 0.6        # overlap bars needed; max share of bars off >1% from the median ratio
MAX_CATCHUP_DAYS = 120                           # longest gap the bot will try to fill from IBKR
FILL_WAIT_S = 20
GW_CONTAINER = os.environ.get("GW_CONTAINER", "ibgw-ibgw-1")   # docker container running IB Gateway
GW_RESTART_AFTER_S = 20 * 60          # restart Gateway if IBKR link has been down this long
GW_RESTART_MIN_GAP_S = 2 * 3600       # and never more often than this

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
from instruments import TICKS as TICK_FOR_REPLAY     # vendor tick sizes, used only by the offline replay

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
        self.link_ok = True          # IBKR server link as reported by Gateway (1100 lost, 1101/1102 back)
        self.lost_since = None
        self.last_gw_restart = 0.0
        self._last_logged = {}

    def _on_error(self, reqId, code, msg, contract=None):
        if code in (2104, 2106, 2107, 2108, 2158, 2119, 2100, 10349, 202, 399):
            return                   # farm status OK, order echo, TIF default: noise
        if code in (1100, 2110):
            if self.link_ok:
                self.link_ok = False
                self.lost_since = self.lost_since or time.time()
                log_event(f"[ib] IBKR link LOST ({code}): Gateway has no connection to IBKR servers")
            return
        if code in (1101, 1102):
            if not self.link_ok:
                down = time.time() - (self.lost_since or time.time())
                log_event(f"[ib] IBKR link restored ({code}) after {down / 60:.0f} min")
            self.link_ok = True; self.lost_since = None
            return
        key = (code, msg[:60]) if reqId == -1 else (code, reqId)
        if reqId == -1 and time.time() - self._last_logged.get(key, 0) < 600:
            return                   # same system message within 10 minutes
        self._last_logged[key] = time.time()
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
                self.link_ok = True   # unknown until Gateway says otherwise; healthy() verifies
                return True
            except SystemExit:
                raise
            except Exception as e:
                log_event(f"connect attempt {attempt + 1} failed: {e}")
                time.sleep(20)
        return False

    def healthy(self):
        """Socket up, Gateway reports an IBKR link, and a trivial request answers fast."""
        if not self.ib.isConnected() or not self.link_ok:
            return False
        old = self.ib.RequestTimeout
        try:
            self.ib.RequestTimeout = 15
            return self.ib.reqCurrentTime() is not None
        except Exception:
            return False
        finally:
            self.ib.RequestTimeout = old

    def restart_gateway(self):
        log_event(f"restarting Gateway container {GW_CONTAINER} (IBKR link down "
                  f"{(time.time() - (self.lost_since or time.time())) / 60:.0f} min)")
        self.last_gw_restart = time.time()
        try: self.ib.disconnect()
        except Exception: pass
        try:
            r = subprocess.run(["docker", "restart", GW_CONTAINER], capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                log_event(f"docker restart failed: {r.stderr.strip()[:200]}")
        except Exception as e:
            log_event(f"docker restart failed: {e}")
        time.sleep(120)              # IBC logs in again

    def ensure(self):
        """Make sure the pass can run. Reconnects, and restarts Gateway when the
        IBKR link has been down for a while. Returns False fast when it cannot."""
        if self.healthy():
            return True
        if self.lost_since is None:
            self.lost_since = time.time()
        log_event("health check failed; reconnecting")
        for _ in range(2):
            try: self.ib.disconnect()
            except Exception: pass
            time.sleep(10)
            if self.connect() and self.healthy():
                self.lost_since = None
                return True
        down = time.time() - self.lost_since
        if down >= GW_RESTART_AFTER_S and time.time() - self.last_gw_restart >= GW_RESTART_MIN_GAP_S:
            self.restart_gateway()
            if self.connect() and self.healthy():
                self.lost_since = None
                return True
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

    def chain(self, s):
        """Every traded month of s, expired ones included, as
        [(last_trade, roll_date, ContractDetails)] sorted by last trade."""
        from ib_async import Future
        spec = MAP[s]
        q = Future(symbol=spec["symbol"], exchange=spec["exchange"], currency=spec["currency"],
                   includeExpired=True)
        if spec["tradingClass"]:
            q.tradingClass = spec["tradingClass"]
        rows = contract_rows(self.ib.reqContractDetails(q) or [], spec)
        if not rows:
            raise DataError("contract unresolved (check ib_contracts.py)")
        return rows

    def order_contract(self, conid, exchange, currency=""):
        """Orders go by contract id only: IBKR rejects the expiry string its own
        contract details return for some exchanges (ICE Europe)."""
        from ib_async import Future
        return Future(conId=conid, exchange=exchange, currency=currency)

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

    def place_resting(self, contract, d, qty, trigger, stop_px, oca):
        """Stop entry at the line with a provisional protective stop attached.
        Both directions share an OCA group so only one can fill."""
        from ib_async import StopOrder
        action, opp = ("BUY", "SELL") if d > 0 else ("SELL", "BUY")
        e = StopOrder(action, qty, trigger); e.tif = "GTC"; e.outsideRth = True; e.transmit = False
        e.ocaGroup = oca; e.ocaType = 1
        et = self.ib.placeOrder(contract, e)
        so = StopOrder(opp, qty, stop_px); so.tif = "GTC"; so.outsideRth = True
        so.parentId = et.order.orderId; so.transmit = True
        stt = self.ib.placeOrder(contract, so)
        return et.order.orderId, stt.order.orderId

    def order_status(self, order_id):
        for t in self.ib.trades():
            if t.order.orderId == order_id:
                return t.orderStatus.status
        return None

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
    if MAP[s].get("tick"):
        return MAP[s]["tick"]
    return details.minTick * (details.priceMagnifier or 1) if details else 0


# ----------------------------------------------------------------------------
# Data layer
# ----------------------------------------------------------------------------
def assemble_series(s, broker, catalog, now_utc, et_today):
    """Vendor history plus IBKR bars, chained through every contract that was
    active since the vendor file ended, ratio adjusted at each hand off exactly
    like a roll. Returns (rows, meta); writes nothing."""
    if s not in catalog:
        raise DataError(f"no vendor file in {DATA_DIR}")
    T, O, H, L, C = load_series(catalog[s])
    rows = [(int(T[i]), float(O[i]), float(H[i]), float(L[i]), float(C[i])) for i in range(len(T))]
    vendor_end = rows[-1][0]
    vendor_end_date = datetime.fromtimestamp(vendor_end, UTC).date()
    active, active_rd = broker.resolve(s, et_today)
    chain = broker.chain(s)
    first = next((i for i, (ltd, rd, d) in enumerate(chain) if rd >= vendor_end_date), len(chain))
    chain = chain[max(0, first - 1):]
    stop = next((i for i, (ltd, rd, d) in enumerate(chain) if d.contract.conId == active.contract.conId), None)
    if stop is None:
        raise DataError("active contract missing from contract chain")
    chain = chain[:stop + 1]

    fetched = []
    for ltd, rd, d in chain:
        c = d.contract
        c.includeExpired = True
        bars = broker.bars_back_to(c, vendor_ts_to_utc(vendor_end) - timedelta(days=5), now_utc)
        bars = sorted({(vendor_ts(b.date), b.open, b.high, b.low, b.close)
                       for b in bars if bar_complete(b, now_utc)})
        fetched.append((d, rd, bars))

    series = {r[0]: r for r in rows}
    cur_end, splices, skipped = vendor_end, [], []
    for i, (d, rd, bars) in enumerate(fetched):
        after = [b for b in bars if b[0] > cur_end]
        window = cur_end - 7 * 86400          # only the days right before the hand off count
        overlap = [(b[4], series[b[0]][4]) for b in bars
                   if window < b[0] <= cur_end and b[0] in series and series[b[0]][4]]
        if len(overlap) < SPLICE_MIN_BARS:
            # thin or expired month: skip it, a later contract in the chain must bridge instead
            skipped.append(f"{d.contract.localSymbol} ({len(overlap)} ovl, {len(after)} after)")
            continue
        ratios = [a / b for a, b in overlap[-240:]]
        med = st.median(ratios)
        off = sum(1 for r in ratios if abs(r / med - 1) > 0.01) / len(ratios)
        if off > SPLICE_MAX_OFF:
            raise DataError(f"splice unstable at {d.contract.localSymbol}: {off:.0%} of {len(ratios)} "
                            f"overlap bars off >1% (wrong contract or misaligned times)")
        rows = [(t, o * med, h * med, l * med, cl * med) for (t, o, h, l, cl) in rows]
        series = {r[0]: r for r in rows}
        if i < len(fetched) - 1:
            boundary = int(datetime(rd.year, rd.month, rd.day, 23, 59, 59, tzinfo=UTC).timestamp())
            nxt_first = min((b[0] for b in fetched[i + 1][2]), default=None)
            seg_end = boundary if nxt_first is None else max(boundary, nxt_first + 12 * 3600)
        else:
            seg_end = float("inf")
        seg = [b for b in after if b[0] <= seg_end]
        rows.extend(seg)
        series.update({b[0]: b for b in seg})
        if seg:
            cur_end = seg[-1][0]
        splices.append(dict(contract=d.contract.localSymbol, ratio=med, overlap=len(overlap),
                            off=round(off, 3), bars=len(seg)))
    if not splices:
        raise DataError("splice: no contract overlaps the series; skipped " + ", ".join(skipped))
    if not any(x["contract"] == active.contract.localSymbol for x in splices):
        skipped.append(f"ACTIVE {active.contract.localSymbol} contributed no bars")
    rows.sort(key=lambda r: r[0])
    c = active.contract
    meta = dict(conId=c.conId, local=c.localSymbol, exchange=c.exchange, currency=c.currency,
                skipped=skipped,
                roll_date=active_rd.isoformat(), vendor_end=iso(vendor_end), splice=splices, rolls=[])
    return rows, meta


def build_cache(s, broker, catalog, now_utc, et_today):
    """First run for a symbol: vendor history spliced to today's active contract."""
    if broker is None:
        T, O, H, L, C = load_series(catalog[s])
        write_cache(s, zip(T.tolist(), O.tolist(), H.tolist(), L.tolist(), C.tolist()))
        write_meta(s, dict(conId=None, local="vendor", splice=None))
        return
    rows, meta = assemble_series(s, broker, catalog, now_utc, et_today)
    write_cache(s, rows)
    write_meta(s, meta)
    log_trade("data_splice", s, contract=meta["local"], bar_time=iso(rows[-1][0]),
              note=" -> ".join(f"{x['contract']} x{x['ratio']:.5g} ({x['overlap']} ovl, {x['off']:.0%} off, "
                               f"{x['bars']} bars)" for x in meta["splice"])
              + (("; skipped " + ", ".join(meta["skipped"])) if meta["skipped"] else ""))


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
        meta.update(conId=c.conId, local=c.localSymbol, exchange=c.exchange, currency=c.currency,
                    roll_date=rd.isoformat())
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


def reconcile(s, T, trades, op, state, broker, details, now_utc, st_scan=None):
    last = len(T) - 1
    last_ts = int(T[last])
    last_done = state["last_bar"].get(s)
    positions = state["positions"]
    P = positions.get(s)
    c = details.contract if details else None
    oc = broker.order_contract(c.conId, c.exchange, c.currency) if (c and broker) else None
    local = c.localSymbol if c else "shadow"
    tick = stop_tick(s, details)
    closed = {(int(T[x["t0"]]), x["dir"]): x for x in trades}
    paper = MODE == "paper" and broker is not None

    # ---- v1 record: every engine trade, executed or not, logged once when the engine closes it.
    # One position at a time per instrument means exits are in time order, so a watermark suffices.
    wm = state.setdefault("engine_logged_through", {})
    executed = state.setdefault("executed", {}).setdefault(s, [])
    if P and P.get("entry_ts") not in executed:
        executed.append(P["entry_ts"])
    if trades:
        newest = max(int(T[x["exit_idx"]]) for x in trades)
        if s not in wm:
            wm[s] = newest                       # first pass: history is not forward data
        else:
            for x in sorted(trades, key=lambda x: x["exit_idx"]):
                xt = int(T[x["exit_idx"]])
                if xt <= wm[s]: continue
                et = int(T[x["t0"]])
                a_t0 = st_scan.A[x["t0"]] if st_scan is not None and st_scan.A[x["t0"]] > 0 else None
                cand = state.get("cand", {}).get(s, {}).get(str(et))
                gate = (f"; gate: {cand['note']}" + ("" if cand["exec"] else " (skipped)")) if cand and cand.get("dir") == x["dir"] else "; gate: no candidate"
                log_trade("engine_trade", s, contract=local, dir=x["dir"], bar_time=iso(et),
                          engine_px=x["entry"], stop=x["stop0"], R_px=abs(x["entry"] - x["stop0"]),
                          R_engine=x["R"], why=x["why"],
                          note=f"exit {iso(xt)} at {x['exit']:.6g}; v1 scored set; "
                               + ("executed" if et in executed else "not executed")
                               + (f"; stop {abs(x['entry'] - x['stop0']) / a_t0:.2f} ATR" if a_t0 else "") + gate)
            wm[s] = newest

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
                old = broker.order_contract(P["con_id"], P.get("exchange") or c.exchange)
                fx, oid = broker.close(old)
                log_trade("roll_close", s, contract=P["local"], dir=P["dir"], qty=P["qty"],
                          bar_time=iso(last_ts), actual_px=fx, order_id=oid)
                spx = round_stop(op["stop"], tick, P["dir"])
                eid, sid, fill, status = broker.place_entry(oc, P["dir"], P["qty"], spx)
                P.update(con_id=c.conId, local=c.localSymbol, exchange=c.exchange, entry_order_id=eid,
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
                    P["stop_order_id"], note = broker.modify_stop(oc, P["stop_order_id"], P["dir"], P["qty"], spx)
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
            if not paper and P.get("fill") is not None:
                bc = P.get("broker_closed")
                actual = bc if bc not in (None, -1) else tr["exit"]
                note = (note + " shadow: exit at engine price").strip() if bc in (None, -1) else (note + " shadow: provisional stop").strip()
            if paper:
                if P.get("broker_closed") is not None:
                    actual = P["broker_closed"] if P["broker_closed"] != -1 else None
                    note = (note + " filled earlier by broker stop").strip()
                else:
                    broker.cancel(P["stop_order_id"])
                    actual, oid = broker.close(broker.order_contract(P["con_id"], P.get("exchange") or c.exchange))
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
    if s not in positions and op is not None and EXEC == "resting":
        t0ts = int(T[op["t0"]])
        if op["t0"] == last and t0ts not in state["missed"]:
            # the engine signalled on the bar that closed but no resting order filled: the
            # line it broke was not in the order set (or the level differed). Not backfilled.
            state["missed"].append(t0ts)
            why_none = state.get("no_order", {}).get(s, {})
            reason = why_none.get("all") or why_none.get(str(op["dir"])) or "line not in the order set, or level differed"
            kind = "gate_skip" if "skip" in reason else "missed_fill"
            log_trade(kind, s, contract=local, dir=op["dir"], bar_time=iso(t0ts),
                      engine_px=op["entry"], stop=op["stop0"], R_px=op["R"],
                      note=f"engine signal without a resting fill ({reason}); not backfilled"
                           + (f"; stop {op['R'] / st.A[op['t0']]:.2f} ATR" if st.A[op['t0']] > 0 else ""))
        elif t0ts not in state["missed"] and (last_done is None or t0ts > last_done):
            state["missed"].append(t0ts)
            log_trade("missed", s, contract=local, dir=op["dir"], bar_time=iso(t0ts),
                      engine_px=op["entry"], R_px=op["R"],
                      note="opened while bot was not running; not backfilled" if last_done else "open at bot start")
    elif s not in positions and op is not None:
        t0ts = int(T[op["t0"]])
        if op["t0"] == last:
            spx = round_stop(op["stop0"], tick, op["dir"])
            P = dict(entry_ts=t0ts, dir=op["dir"], entry=op["entry"], stop0=op["stop0"],
                     stop=op["stop"], R=op["R"], phase=op["phase"], qty=QTY,
                     con_id=c.conId if c else None, local=local, exchange=c.exchange if c else None, fill=None,
                     entry_order_id=None, stop_order_id=None, broker_closed=None,
                     opened=datetime.now(UTC).isoformat(timespec="seconds"))
            why = f"{op['kind']} line; {len(op['tch'])} touches; span {op['t0'] - op['a']} bars; stop {op['stop_src']}"
            log_trade("signal", s, contract=local, dir=op["dir"], qty=QTY, bar_time=iso(t0ts),
                      engine_px=op["entry"], stop=op["stop0"], R_px=op["R"], why=why)
            if paper:
                eid, sid, fill, status = broker.place_entry(oc, op["dir"], QTY, spx)
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
# Resting order execution
# ----------------------------------------------------------------------------
def round_trigger(px, tick, d):
    """Stop entry rounded to the tick on the far side of the line, so a fill
    guarantees the engine's break condition held."""
    if not tick:
        return px
    k = px / tick
    k = math.floor(k + 1e-9) if d < 0 else math.ceil(k - 1e-9)
    return round(k * tick, 10)


def settle_resting(s, state, broker, st, T, op, details, tick):
    """Resolve the orders rested at the previous pass against the bar that just
    closed: filled or not, and if filled, confirmed by the engine or scratched."""
    orders = state["resting"].pop(s, [])
    if not orders:
        return
    last = len(T) - 1; last_ts = int(T[last])
    paper = MODE == "paper" and broker is not None
    c = details.contract if details else None
    oc = broker.order_contract(c.conId, c.exchange, c.currency) if (c and broker) else None
    local = c.localSymbol if c else "shadow"
    O, H, L, C, A = st.O[last], st.H[last], st.L[last], st.C[last], (st.A[last] or 1e-12)
    for o in orders:
        d = o["dir"]
        if last < 1 or int(o.get("placed_after", -1)) != int(T[last - 1]):
            # more than one bar has closed since this order was placed (a missed pass): the
            # order was for a bar we did not see close, so it is cancelled and not interpreted
            if paper: broker.cancel(o["entry_order_id"])
            log_trade("rest_stale", s, contract=local, dir=d, bar_time=iso(o.get("placed_after", last_ts)),
                      engine_px=o["trigger"], note="order outlived its bar; cancelled, not interpreted")
            continue
        fill, stop_hit = None, None
        if paper:
            fill = broker.fill_of(o["entry_order_id"])
            if fill is not None:
                stop_hit = broker.fill_of(o["stop_order_id"])
            else:
                broker.cancel(o["entry_order_id"])
        else:
            touched = (L <= o["trigger"]) if d < 0 else (H >= o["trigger"])
            if touched:
                fill = min(O, o["trigger"]) if d < 0 else max(O, o["trigger"])
                if (d < 0 and H >= o["stop"]) or (d > 0 and L <= o["stop"]):
                    stop_hit = o["stop"]          # conservative: assume the provisional stop fired
        if fill is None:
            continue
        confirmed = op is not None and op["t0"] == last and op["dir"] == d
        log_trade("rest_fill", s, contract=local, dir=d, qty=o["qty"], bar_time=iso(last_ts),
                  engine_px=o["trigger"], actual_px=fill, stop=o["stop"], order_id=o["entry_order_id"],
                  note=f"line {o['line_level']:.6g} refit {o['refit_level']:.6g}" +
                       (f"; provisional stop filled {stop_hit:.6g}" if stop_hit is not None else ""))
        if confirmed:
            P = dict(entry_ts=last_ts, dir=d, entry=op["entry"], stop0=op["stop0"], stop=o["stop"],
                     R=op["R"], phase=op["phase"], qty=o["qty"], con_id=c.conId if c else None, local=local,
                     exchange=c.exchange if c else None, fill=fill, entry_order_id=o["entry_order_id"],
                     stop_order_id=o["stop_order_id"], broker_closed=stop_hit if stop_hit is not None else None,
                     opened=datetime.now(UTC).isoformat(timespec="seconds"), via="resting")
            state["positions"][s] = P
            log_trade("confirm", s, contract=local, dir=d, qty=o["qty"], bar_time=iso(last_ts),
                      engine_px=op["entry"], actual_px=fill, stop=op["stop0"], R_px=op["R"],
                      why=f"{op['kind']} line; {len(op['tch'])} touches; stop {op['stop_src']}",
                      note="fill vs engine " + f"{(fill - op['entry']) * d / op['R']:+.3f}R"
                           + (f"; tier {o['score']:+.3f}" if o.get("score") is not None else "")
                           + f"; stop {op['R'] / A:.2f} ATR")
        else:
            exit_px, oid, note = None, None, ""
            if stop_hit is not None:
                exit_px, note = stop_hit, "closed by provisional stop"
            elif paper:
                broker.cancel(o["stop_order_id"])
                exit_px, oid = broker.close(oc)
                if exit_px is None:
                    exit_px = broker.fill_of(o["stop_order_id"]); note = "already flat"
            else:
                exit_px = C
            pnl_atr = ((exit_px - fill) * d / A) if exit_px is not None else None
            log_trade("scratch", s, contract=local, dir=d, qty=o["qty"], bar_time=iso(last_ts),
                      engine_px=o["trigger"], actual_px=fill, order_id=oid,
                      note=(f"engine did not confirm; exit {exit_px:.6g}, {pnl_atr:+.3f} ATR " if exit_px is not None
                            else "engine did not confirm; exit unknown ") + note)


def place_resting(s, state, broker, st, taken, op, details, tick):
    """Rest at most one stop order per direction for the next bar, only when
    both the bot and the engine are flat."""
    if s in state["positions"] or op is not None:
        state.setdefault("no_order", {})[s] = {"all": "in position at placement", "ts": int(st.T[-1])}
        return
    state.setdefault("no_order", {}).pop(s, None)
    orders = next_bar_orders(st, taken)
    if not orders:
        return
    T = st.T; last_ts = int(T[-1])
    paper = MODE == "paper" and broker is not None
    c = details.contract if details else None
    oc = broker.order_contract(c.conId, c.exchange, c.currency) if (c and broker) else None
    oca = f"{s}-{last_ts}"
    placed, skipped = [], []
    for d, o in orders.items():
        score, gate_note, stop_atr = None, "", None
        if PROTOCOL in ("v2", "v3") and TIER is not None:
            ok, score, stop_atr, gate_note = TIER.allows(s, st, o, last_ts + 3600, stop_rule=(PROTOCOL == "v3"))
            cands = state.setdefault("cand", {}).setdefault(s, {})
            cands[str(last_ts + 3600)] = dict(dir=d, score=score, stop_atr=stop_atr, exec=ok, note=gate_note)
            for k in [k for k in cands if int(k) < last_ts - 7 * 86400]: del cands[k]
            if not ok:
                skipped.append(f"{'short' if d < 0 else 'long'} @{o['trigger']:.6g} {PROTOCOL} skip: {gate_note}")
                state.setdefault("no_order", {})[s] = {str(d): f"{PROTOCOL} skip: {gate_note}", "ts": last_ts}
                continue
        trigger = round_trigger(o["trigger"], tick, d)
        spx = round_stop(o["stop"], tick, d)
        rec = dict(dir=d, trigger=trigger, stop=spx, edge=list(o["edge"]), line_level=o["line_level"],
                   refit_level=o["refit_level"], qty=QTY, placed_after=last_ts, entry_order_id=None,
                   stop_order_id=None, score=score, stop_atr=stop_atr)
        if paper:
            rec["entry_order_id"], rec["stop_order_id"] = broker.place_resting(oc, d, QTY, trigger, spx, oca)
        placed.append(rec)
    if placed:
        state["resting"][s] = placed
    msg = "  ".join(f"{'short' if r['dir'] < 0 else 'long'} @{r['trigger']:.6g} stop {r['stop']:.6g}"
                    + (f" score {r['score']:+.3f}" if r.get("score") is not None else "")
                    + (f" {r['stop_atr']:.2f}ATR" if r.get("stop_atr") is not None else "") for r in placed)
    if skipped:
        msg += ("  | " if msg else "") + "  ".join(skipped)
    log_event(f"rest {s:5s} " + msg)


# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        s = json.load(open(STATE_FILE))
    else:
        s = dict(mode=MODE, positions={}, last_bar={}, missed=[], excluded={}, resting={},
                 started=datetime.now(UTC).isoformat(timespec="seconds"))
    s.setdefault("resting", {})
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
    if broker is not None and not broker.ensure():
        down = (time.time() - broker.lost_since) / 60 if broker.lost_since else 0
        log_trade("gap", "ALL", note=f"pass skipped: IBKR not reachable (down {down:.0f} min); "
                                     f"logged per protocol, clock extends")
        log_event("pass skipped: IBKR not reachable")
        return
    if broker is not None:
        try:
            broker.ib.reqAllOpenOrders(); broker.ib.sleep(1)
        except Exception as e:
            log_event(f"reqAllOpenOrders failed: {e}")
    t_start = time.time(); fails = 0
    for s in syms:
        if broker is not None and (not broker.ib.isConnected() or not broker.link_ok or
                                   (fails >= 3 and not broker.healthy())):
            log_trade("gap", "ALL", note=f"IBKR link lost mid pass at {s}; rest of the pass skipped")
            log_event("IBKR link lost mid pass; rest of the pass skipped"); break
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
            if new == 0 and broker is not None and s not in state["positions"] and not state["resting"].get(s):
                continue                        # nothing new, nothing held, nothing resting
            T, trades, op = run_engine(s)
            st, taken = None, set()
            tick = stop_tick(s, details)
            if EXEC == "resting":
                st = scan(cache_path(s), int(T.min()) + WARMUP_DAYS * 86400)
                taken, _ = taken_edges(st, trades + ([op] if op else []))
                settle_resting(s, state, broker, st, T, op, details, tick)
            reconcile(s, T, trades, op, state, broker, details, now_utc, st)
            if EXEC == "resting":
                place_resting(s, state, broker, st, taken, op, details, tick)
            fails = 0
        except DataError as e:
            if state["excluded"].get(s) != str(e):
                state["excluded"][s] = str(e)
                log_trade("excluded", s, note=str(e))
        except Exception as e:
            fails += 1
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
    global TIER
    if PROTOCOL in ("v2", "v3"):
        from tier import Tier, STOP_MAX_ATR
        TIER = Tier()
        log_event(f"protocol {PROTOCOL}: tier cutoff {TIER.cutoff:+.4f} (fit {TIER.fit_years}), cost cap {TIER.cost_cap}R, "
                  f"{len(TIER.cheap)} instruments pass the cap"
                  + (f", stop within {STOP_MAX_ATR} ATR" if PROTOCOL == "v3" else ""))

    if "--replay" in args:
        return replay(int(args[args.index("--replay") + 1]), args[args.index("--replay") + 2], catalog)

    state = load_state()
    broker = Broker()
    if not broker.connect():
        sys.exit("could not connect to IBKR Gateway")
    log_event(f"forward test runner: {MODE} mode, {EXEC} execution, protocol {PROTOCOL}, {len(syms)} symbols, data from {DATA_DIR}")
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
        st, taken = None, set()
        if EXEC == "resting":
            st = scan(cache_path(s), int(Tc.min()) + WARMUP_DAYS * 86400)
            taken, _ = taken_edges(st, trades + ([op] if op else []))
            settle_resting(s, state, None, st, Tc, op, None, TICK_FOR_REPLAY.get(s, 0.0))
        reconcile(s, Tc, trades, op, state, None, None, datetime.now(UTC), st)
        if EXEC == "resting":
            place_resting(s, state, None, st, taken, op, None, TICK_FOR_REPLAY.get(s, 0.0))
        save_state(state)
    print(f"\nreplay done -> {TRADE_LOG}")
    if os.path.exists(TRADE_LOG):
        counts = defaultdict(int)
        for r in csv.DictReader(open(TRADE_LOG)):
            counts[r["event"]] += 1
            if r["event"] != "stop_move":
                print(f"  {r['event']:11s} {r['bar_time']:16s} dir {r['dir']:>2s} engine {r['engine_px']:>10s} "
                      f"fill {r['actual_px']:>10s} stop {r['stop']:>10s} R {r['R_engine']:>7s} {r['note']}")
        print("  counts:", dict(counts))
        diffs = []
        for r in csv.DictReader(open(TRADE_LOG)):
            if r["event"] == "confirm" and "fill vs engine" in r["note"]:
                try: diffs.append(float(r["note"].split("fill vs engine")[1].strip().rstrip("R")))
                except ValueError: pass
        if diffs:
            print(f"  confirmed fills: {len(diffs)}, fill vs engine price avg {sum(diffs) / len(diffs):+.4f}R")


if __name__ == "__main__":
    main()
