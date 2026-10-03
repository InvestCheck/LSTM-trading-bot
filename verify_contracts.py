#!/usr/bin/env python3
"""Check every frozen instrument against IBKR before the live bot is built.

For each symbol it reports:
  contract   does the ib_contracts.py row resolve, and which month the
             protocol roll rule would trade today, with its roll date
  data       can the account pull 1 hour bars for it (market data permission)
  trade      can the account trade it (what if order, nothing is placed)
  splice     do IBKR bars line up with the FirstRateData file: the price ratio
             at matching timestamps should be STABLE. A stable ratio far from
             1.0 is fine (unit difference, e.g. cents vs dollars, or a
             different contract month); an unstable one means a wrong
             contract or misaligned timestamps.

Places no orders. Writes contract_check.csv.

Usage (repo folder, Gateway logged in on port 4002):
  python3 verify_contracts.py DATA_DIR
  python3 verify_contracts.py DATA_DIR GC ZN FDAX     only these symbols
"""
import sys, csv, statistics as st
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from ib_async import IB, Future, MarketOrder
from batch_backtest import build_catalog
from backtest_hull import load_series
from ib_contracts import IB as MAP, UNIVERSE, pick_active

ET = ZoneInfo("America/New_York")
PORT = 4002


def vendor_ts(dt_utc):
    """IBKR bar time -> the data files' convention (US Eastern wall clock
    stored as if it were UTC)."""
    return int(dt_utc.astimezone(ET).replace(tzinfo=timezone.utc).timestamp())


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 verify_contracts.py DATA_DIR [SYM ...]")
    cat = build_catalog(sys.argv[1])
    syms = sys.argv[2:] or UNIVERSE

    ib = IB()
    ib.connect("127.0.0.1", PORT, clientId=9, timeout=20)
    ib.RequestTimeout = 30          # never hang forever on a request IBKR ignores
    acct = ib.managedAccounts()
    if not any(a.startswith("DU") for a in acct):
        sys.exit(f"refusing: not a paper account {acct}")
    errs = []
    ib.errorEvent += lambda reqId, code, msg, contract=None: errs.append((code, msg))
    today = datetime.now(timezone.utc).date()
    out = []

    for s in syms:
        spec = MAP[s]
        row = dict(sym=s, contract="", local="", roll="", min_tick="", mult="",
                   data="", trade="", margin="", ratio="", ratio_spread="", note="")
        out.append(row)
        print(f"{s:6s} ", end="", flush=True)

        q = Future(symbol=spec["symbol"], exchange=spec["exchange"], currency=spec["currency"])
        if spec["tradingClass"]:
            q.tradingClass = spec["tradingClass"]
        errs.clear()
        det = ib.reqContractDetails(q)
        if not det:
            row["contract"] = "FAIL"
            row["note"] = "; ".join(m for _, m in errs)[:120] or "no contracts returned"
            print(f"contract FAIL  {row['note']}"); continue
        d, rd = pick_active(det, spec, today)
        if d is None:
            row["contract"] = "FAIL"; row["note"] = "no traded month ahead of its roll date"
            print("contract FAIL  no active month"); continue
        c = d.contract
        row.update(contract="OK", local=c.localSymbol, roll=rd.isoformat(),
                   min_tick=d.minTick, mult=c.multiplier)

        # data: recent bars, and bars around the end of the data file for the splice
        errs.clear()
        bars = ib.reqHistoricalData(c, "", "5 D", "1 hour", "TRADES", useRTH=False,
                                    formatDate=2, timeout=60)
        row["data"] = "OK" if bars else "FAIL"
        if not bars:
            row["note"] = "; ".join(m for _, m in errs)[:120]

        if bars and s in cat:
            T, O, H, L, C = load_series(cat[s])
            vend = {int(T[i]): C[i] for i in range(len(T))}
            seed_end = datetime.fromtimestamp(int(T.max()), timezone.utc).replace(tzinfo=ET)
            errs.clear()
            old = ib.reqHistoricalData(c, seed_end.astimezone(timezone.utc) + timedelta(hours=2),
                                       "10 D", "1 hour", "TRADES", useRTH=False,
                                       formatDate=2, timeout=60)
            ratios = [b.close / vend[vendor_ts(b.date)] for b in (old or [])
                      if vendor_ts(b.date) in vend and vend[vendor_ts(b.date)]]
            if len(ratios) >= 10:
                r = ratios[-48:]
                med = st.median(r)
                spread = max(abs(x / med - 1) for x in r)
                row["ratio"] = f"{med:.6g}"
                row["ratio_spread"] = f"{spread:.2%}"
                if spread > 0.003:
                    row["note"] = (row["note"] + " splice unstable").strip()
            else:
                row["ratio"] = "n/a"
                row["note"] = (row["note"] + f" only {len(ratios)} matching bars at data end").strip()
        elif s not in cat:
            row["note"] = (row["note"] + " not in data dir").strip()

        # trading permission: what if order, nothing is placed
        errs.clear()
        try:
            state = ib.whatIfOrder(c, MarketOrder("BUY", 1))
            init = getattr(state, "initMarginChange", "") if state else ""
            ok = bool(init) and not str(init).startswith("1.7976")
        except Exception as e:
            ok = False; errs.append((0, str(e)))
        row["trade"] = "OK" if ok else "FAIL"
        if ok:
            try: row["margin"] = f"{float(init):,.0f}"
            except ValueError: row["margin"] = str(init)
        else:
            row["note"] = (row["note"] + " " + "; ".join(m for _, m in errs)[:120]).strip()

        print(f"{row['local']:10s} roll {row['roll']}  tick {row['min_tick']}  "
              f"data {row['data']:4s} trade {row['trade']:4s} margin {row['margin']:>9s}  "
              f"ratio {row['ratio']} ({row['ratio_spread']})  {row['note']}")
        ib.sleep(0.5)

    ib.disconnect()
    with open("contract_check.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    def bad(k): return [r["sym"] for r in out if r[k] != "OK"]
    unstable = [r["sym"] for r in out if "unstable" in r["note"] or "matching bars" in r["note"]]
    print("\nSUMMARY")
    print(f"  contract fails : {' '.join(bad('contract')) or 'none'}")
    print(f"  no data        : {' '.join(bad('data')) or 'none'}")
    print(f"  no trading     : {' '.join(bad('trade')) or 'none'}")
    print(f"  splice issues  : {' '.join(unstable) or 'none'}")
    margins = [float(r["margin"].replace(",", "")) for r in out
               if r["margin"] and r["margin"].replace(",", "").replace(".", "").isdigit()]
    if margins:
        print(f"  margin if all 70 open at once: about {sum(margins):,.0f} (account currency)")
    print("  full table -> contract_check.csv")


if __name__ == "__main__":
    main()
