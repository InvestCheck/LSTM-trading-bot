#!/usr/bin/env python3
"""One off: close the three broker positions the bot does not track (RZ6 long,
HEZ6 short, KEZ6 short, 2 Nov 2026) and cancel the two orphan buy stops left
behind by the stale resting orders. Touches nothing else: no state file, no
trade log, no other orders.

Run on the droplet, repo folder:  venv/bin/python cleanup_orphans.py
"""
from ib_async import IB, Future, MarketOrder

TARGETS = {"RZ6", "HEZ6", "KEZ6"}          # localSymbols to flatten
STRAY_STOPS = {("HEZ6", "BUY", "STP"), ("KEZ6", "BUY", "STP")}

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=0, timeout=30)   # client 0 can see and cancel every client's orders
ib.reqPositions(); ib.sleep(2)
trades = ib.reqAllOpenOrders(); ib.sleep(2)

print("before: positions", [(p.contract.localSymbol, p.position) for p in ib.positions()])
for t in trades:
    key = (t.contract.localSymbol, t.order.action, t.order.orderType)
    if key in STRAY_STOPS:
        print(f"cancelling {key} @ {t.order.auxPrice} (status {t.orderStatus.status})")
        ib.cancelOrder(t.order)
ib.sleep(3)
still = [(t.contract.localSymbol, t.order.action, t.orderStatus.status) for t in ib.reqAllOpenOrders()
         if (t.contract.localSymbol, t.order.action, t.order.orderType) in STRAY_STOPS and t.orderStatus.status not in ("Cancelled", "ApiCancelled", "Inactive")]
print("stray stops still open after cancel:", still or "none")

for p in ib.positions():
    if p.contract.localSymbol not in TARGETS or p.position == 0:
        continue
    c = Future(conId=p.contract.conId); ib.qualifyContracts(c)
    o = MarketOrder("SELL" if p.position > 0 else "BUY", abs(int(p.position))); o.tif = "GTC"; o.outsideRth = True
    tr = ib.placeOrder(c, o)
    for _ in range(90):
        ib.sleep(1)
        if tr.orderStatus.status == "Filled": break
    print(f"{p.contract.localSymbol}: {o.action} {o.totalQuantity} -> {tr.orderStatus.status} @ {tr.orderStatus.avgFillPrice}")

ib.reqPositions(); ib.sleep(2)
print("after: positions", [(p.contract.localSymbol, p.position) for p in ib.positions()] or "none")
print("after: open orders on the three", [(t.contract.localSymbol, t.order.action, t.order.orderType, t.orderStatus.status)
                                           for t in ib.reqAllOpenOrders() if t.contract.localSymbol in TARGETS] or "none")
ib.disconnect()
