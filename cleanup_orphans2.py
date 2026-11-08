#!/usr/bin/env python3
"""Second half of the 2 Nov 2026 cleanup: sell the orphan RZ6 (gilt) long by
contract id, and clear the two orphan buy stops with a global cancel. The global
cancel removes every open order on the account, so this refuses to run if the
bot's state file shows a held position (it would take that position's protective
stop with it). Resting entry orders are re placed by the bot on its next pass.

Run on the droplet, repo folder:  venv/bin/python cleanup_orphans2.py
"""
import json, os, sys
from ib_async import IB, Contract, MarketOrder

state = json.load(open("live_state.json")) if os.path.exists("live_state.json") else {}
if state.get("positions"):
    sys.exit(f"bot holds {list(state['positions'])}; a global cancel would drop its stop. Not running.")

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=0, timeout=30)
ib.reqPositions(); ib.sleep(2)
print("before: positions", [(p.contract.localSymbol, p.position) for p in ib.positions()])
print("before: open orders", len(ib.reqAllOpenOrders()))

ib.reqGlobalCancel(); ib.sleep(4)
left = [(t.contract.localSymbol, t.order.action, t.order.orderType, t.orderStatus.status) for t in ib.reqAllOpenOrders()
        if t.orderStatus.status not in ("Cancelled", "ApiCancelled", "Inactive")]
print("open orders after global cancel:", left or "none")

for p in ib.positions():
    if p.contract.localSymbol != "RZ6" or p.position == 0:
        continue
    c = Contract(conId=p.contract.conId, exchange="ICEEU")        # by id only: no expiry string for IB to reject
    o = MarketOrder("SELL" if p.position > 0 else "BUY", abs(int(p.position))); o.tif = "GTC"
    tr = ib.placeOrder(c, o)
    for _ in range(90):
        ib.sleep(1)
        if tr.orderStatus.status in ("Filled", "Cancelled", "Inactive"): break
    print(f"RZ6: {o.action} {o.totalQuantity} -> {tr.orderStatus.status} @ {tr.orderStatus.avgFillPrice}")
    if tr.orderStatus.status != "Filled": print(tr.log[-1].message if tr.log else "")

ib.reqPositions(); ib.sleep(2)
print("after: positions", [(p.contract.localSymbol, p.position) for p in ib.positions()] or "none")
ib.disconnect()
