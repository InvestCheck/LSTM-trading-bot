"""Read back (and optionally cancel) IBKR orders. Run with the bot stopped.

  python3 check_orders.py                 list orders, positions, balances
  python3 check_orders.py --cancel 12 17  cancel those order ids
  python3 check_orders.py --cancel-day    cancel any working DAY orders (the stray duplicate)
"""
import sys
from ib_async import IB

HOST, PORT, CLIENT_ID = "127.0.0.1", 4002, 9   # paper Gateway; client id 9 stays clear of the bot (id 1)

ib = IB()
ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
print("connected:", ib.managedAccounts())

ib.reqAllOpenOrders()
ib.sleep(1)
trades = ib.openTrades()

print(f"\n--- OPEN ORDERS ({len(trades)}) ---")
for t in trades:
    c, o, s = t.contract, t.order, t.orderStatus
    px = o.lmtPrice or o.auxPrice or "MKT"
    print(f"id={o.orderId:<4} {c.localSymbol:8s} {o.action:4s} {o.totalQuantity:>3} {o.orderType:5s} @ {px}  tif={o.tif}  status={s.status}")

# ---- optional cancels -------------------------------------------------
to_cancel = []
if "--cancel-day" in sys.argv:
    to_cancel = [t for t in trades if t.order.tif == "DAY"]
elif "--cancel" in sys.argv:
    ids = {int(a) for a in sys.argv[sys.argv.index("--cancel") + 1:] if a.isdigit()}
    to_cancel = [t for t in trades if t.order.orderId in ids]

if to_cancel:
    print(f"\n--- CANCELLING ({len(to_cancel)}) ---")
    for t in to_cancel:
        ib.cancelOrder(t.order)
        print(f"cancel sent: id={t.order.orderId} {t.contract.localSymbol} {t.order.action} tif={t.order.tif}")
    ib.sleep(2)

positions = ib.positions()
print(f"\n--- POSITIONS ({len(positions)}) ---")
for p in positions:
    print(f"{p.contract.localSymbol:8s} qty={p.position:>4}  avgCost={p.avgCost:.4f}")

print("\n--- ACCOUNT ---")
for v in ib.accountValues():
    if v.tag in ("NetLiquidation", "AvailableFunds", "BuyingPower") and v.currency == "USD":
        print(f"{v.tag:16s} {v.value}")

ib.disconnect()
