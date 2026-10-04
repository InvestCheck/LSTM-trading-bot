#!/usr/bin/env python3
"""Print the vendor vs IBKR overlap for one symbol so a bad splice can be read
by eye: timestamp, vendor close, IBKR close, ratio, for the first contract in
the chain.

Usage (Gateway logged in):  python3 show_overlap.py DATA_DIR SYM
"""
import os, sys, statistics as st
from datetime import datetime, timezone, timedelta

os.environ.setdefault("MODE", "shadow")
import live_ibkr
from live_ibkr import Broker, ET, vendor_ts, vendor_ts_to_utc, bar_complete
from backtest_hull import load_series
from batch_backtest import build_catalog, iso


def main():
    data_dir, s = sys.argv[1], sys.argv[2]
    live_ibkr.DATA_DIR = data_dir
    T, O, H, L, C = load_series(build_catalog(data_dir)[s])
    vend = {int(t): float(c) for t, c in zip(T.tolist(), C.tolist())}
    vendor_end = int(T[-1])
    print(f"{s}: vendor file ends {iso(vendor_end)}, last close {C[-1]:.6g}, {len(T)} bars")
    b = Broker(); b.connect()
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    chain = b.chain(s)
    vendor_end_date = datetime.fromtimestamp(vendor_end, timezone.utc).date()
    first = next((i for i, (ltd, rd, d) in enumerate(chain) if rd >= vendor_end_date), len(chain))
    for ltd, rd, d in chain[max(0, first - 1):first + 2]:
        c = d.contract; c.includeExpired = True
        bars = [x for x in b.bars_back_to(c, vendor_ts_to_utc(vendor_end) - timedelta(days=5), now)
                if bar_complete(x, now)]
        pairs = [(vendor_ts(x.date), vend[vendor_ts(x.date)], x.close) for x in bars
                 if vendor_ts(x.date) in vend and vendor_ts(x.date) <= vendor_end]
        print(f"\n{c.localSymbol}: last trade {ltd}, roll {rd}, {len(bars)} bars fetched, {len(pairs)} overlap vendor")
        if pairs:
            rs = [i / v for _, v, i in pairs if v]
            print(f"  ratio median {st.median(rs):.6g}, min {min(rs):.6g}, max {max(rs):.6g}")
            print("  time (vendor convention)  vendor     ibkr       ratio")
            for t, v, i in pairs[-30:]:
                print(f"  {iso(t)}  {v:<10.6g} {i:<10.6g} {i / v if v else 0:.5f}")
        if bars:
            print(f"  IBKR bars span {bars[0].date:%Y-%m-%d %H:%M} .. {bars[-1].date:%Y-%m-%d %H:%M} UTC")
    b.ib.disconnect()


if __name__ == "__main__":
    main()
