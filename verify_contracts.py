#!/usr/bin/env python3
"""Check every frozen instrument against IBKR using the bot's own code path.

For each symbol:
  contract  the ib_contracts.py row resolves, and which month the protocol
            trades today with its roll date
  splice    live_ibkr.assemble_series() builds the full series: vendor history
            chained through every contract since the vendor file ended, ratio
            adjusted at each hand off. Reports each hand off and the bars
            appended since the vendor end. Writes nothing.
  trade     what if order by contract id (nothing is placed), with margin

Usage (repo folder, Gateway logged in):
  python3 verify_contracts.py DATA_DIR
  python3 verify_contracts.py DATA_DIR GC ZN FDAX     only these symbols
"""
import os, sys, csv
from datetime import datetime, timezone

os.environ.setdefault("MODE", "shadow")
import live_ibkr
from live_ibkr import Broker, DataError, assemble_series, ET
from batch_backtest import build_catalog
from ib_contracts import UNIVERSE


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 verify_contracts.py DATA_DIR [SYM ...]")
    live_ibkr.DATA_DIR = sys.argv[1]
    catalog = build_catalog(sys.argv[1])
    syms = sys.argv[2:] or UNIVERSE

    broker = Broker()
    if not broker.connect():
        sys.exit("could not connect to Gateway on 4002")
    if not (broker.account or "").startswith("DU"):
        sys.exit(f"refusing: {broker.account} is not a paper account")
    from ib_async import MarketOrder
    errs = []
    broker.ib.errorEvent += lambda reqId, code, msg, contract=None: errs.append((code, msg))

    now_utc = datetime.now(timezone.utc)
    et_today = now_utc.astimezone(ET).date()
    out = []
    for s in syms:
        row = dict(sym=s, contract="", local="", roll="", tick="", mult="", splice="",
                   chain="", bars_since_vendor="", trade="", margin="", note="")
        out.append(row)
        print(f"{s:5s} ", end="", flush=True)
        try:
            d, rd = broker.resolve(s, et_today)
        except DataError as e:
            row["contract"], row["note"] = "FAIL", str(e)
            print(f"contract FAIL  {e}"); continue
        c = d.contract
        row.update(contract="OK", local=c.localSymbol, roll=rd.isoformat(),
                   tick=round(d.minTick * (d.priceMagnifier or 1), 10), mult=c.multiplier)

        try:
            rows, meta = assemble_series(s, broker, catalog, now_utc, et_today)
            since = sum(x["bars"] for x in meta["splice"])
            row.update(splice="OK", bars_since_vendor=since,
                       chain=" -> ".join(f"{x['contract']} x{x['ratio']:.4g} ({x['off']:.0%} off)"
                                         for x in meta["splice"]))
            if any(x["off"] > 0.25 for x in meta["splice"]):
                row["note"] = "noisy overlap (different month between vendor and IBKR; ratio still usable)"
        except DataError as e:
            row["splice"], row["note"] = "FAIL", str(e)
        except Exception as e:
            row["splice"], row["note"] = "FAIL", f"{type(e).__name__}: {e}"

        errs.clear()
        try:
            o = MarketOrder("BUY", 1); o.tif = "GTC"
            state = broker.ib.whatIfOrder(broker.order_contract(c.conId, c.exchange, c.currency), o)
            init = getattr(state, "initMarginChange", "") if state else ""
            ok = bool(init) and not str(init).startswith("1.7976")
        except Exception as e:
            ok = False; errs.append((0, str(e)))
        row["trade"] = "OK" if ok else "FAIL"
        if ok:
            try: row["margin"] = f"{float(init):,.0f}"
            except ValueError: row["margin"] = str(init)
        else:
            row["note"] = (row["note"] + " | " + "; ".join(m for _, m in errs)[:140]).strip(" |")

        print(f"{row['local']:12s} roll {row['roll']}  tick {row['tick']}  splice {row['splice']:4s} "
              f"+{row['bars_since_vendor']} bars  trade {row['trade']:4s} margin {row['margin']:>9s}  "
              f"{row['chain']}  {row['note']}")
        broker.ib.sleep(0.3)

    broker.ib.disconnect()
    with open("contract_check.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    def bad(k): return [r["sym"] for r in out if r[k] != "OK"]
    margins = [float(r["margin"].replace(",", "")) for r in out
               if r["margin"] and r["margin"].replace(",", "").replace(".", "").isdigit()]
    print("\nSUMMARY")
    print(f"  contract fails : {' '.join(bad('contract')) or 'none'}")
    print(f"  splice fails   : {' '.join(bad('splice')) or 'none'}")
    print(f"  no trading     : {' '.join(bad('trade')) or 'none'}")
    print(f"  fully OK       : {sum(1 for r in out if r['contract'] == r['splice'] == r['trade'] == 'OK')}/{len(out)}")
    if margins:
        print(f"  margin if all open at once: about {sum(margins):,.0f}")
    print("  full table -> contract_check.csv")


if __name__ == "__main__":
    main()
