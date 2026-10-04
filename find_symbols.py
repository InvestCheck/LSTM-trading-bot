#!/usr/bin/env python3
"""Try candidate IBKR identifiers for the symbols verify_contracts.py could
not resolve, and print what each candidate returns.

Usage (Gateway logged in):  python3 find_symbols.py
"""
from ib_async import IB, Future

CANDIDATES = {
    "MP (peso)": [("MXP", "CME", "USD"), ("MXN", "CME", "USD"), ("6M", "CME", "USD"), ("MP", "CME", "USD"), ("MXP", "CME", "MXN")],
    "MFS (round 2)": [("M1EA", "CME", "USD"), ("MXEA", "CFE", "USD"), ("MXEA", "CBOE", "USD"), ("MFS", "ICEEU", "USD")],
    "MME (round 2)": [("M1EF", "CME", "USD"), ("MXEF", "CFE", "USD"), ("MXEF", "CBOE", "USD"), ("MME", "ICEEU", "USD")],
    "B":   [("COIL", "IPE", "USD"), ("COIL", "ICEEU", "USD"), ("BRN", "IPE", "USD"), ("B", "IPE", "USD")],
    "CNH": [("CNH", "CME", "CNH"), ("CNH", "CME", "USD"), ("USDCNH", "CME", "CNH")],
    "DC":  [("DA", "CME", "USD"), ("DC", "CME", "USD"), ("DCS", "CME", "USD"), ("MILK", "CME", "USD")],
    "MFS": [("MFS", "NYBOT", "USD"), ("MFS", "ICEUS", "USD"), ("EAFE", "NYBOT", "USD"), ("MXEA", "NYBOT", "USD"), ("MFS", "NYSELIFFE", "USD")],
    "MME": [("MME", "NYBOT", "USD"), ("MME", "ICEUS", "USD"), ("MXEF", "NYBOT", "USD"), ("MME", "NYSELIFFE", "USD")],
    "RP":  [("RP", "CME", "GBP"), ("RP", "CME", "USD"), ("EURGBP", "CME", "GBP")],
    "RY":  [("RY", "CME", "JPY"), ("RY", "CME", "USD"), ("EURJPY", "CME", "JPY")],
    "XC":  [("YC", "CBOT", "USD"), ("XC", "CBOT", "USD"), ("ZC", "CBOT", "USD")],
}
KEYWORDS = {"MP (peso)": "mexican peso", "MFS (round 2)": "MSCI EAFE", "MME (round 2)": "MSCI emerging", "B": "brent", "CNH": "offshore", "DC": "milk", "MFS": "MSCI EAFE", "MME": "MSCI emerging",
            "RP": "EUR/GBP", "RY": "EUR/JPY", "XC": "mini corn"}


def main():
    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=12, timeout=20)
    ib.RequestTimeout = 20
    for s, cands in CANDIDATES.items():
        print(f"\n== {s}")
        for sym, exch, cur in cands:
            try:
                det = ib.reqContractDetails(Future(symbol=sym, exchange=exch, currency=cur))
            except Exception as e:
                det = []
            if det:
                d = det[0]
                classes = sorted({(x.contract.tradingClass, x.contract.multiplier) for x in det})
                print(f"  OK   {sym:7s} {exch:9s} {cur}  -> {d.longName} | class/mult {classes} | "
                      f"tick {d.minTick}x{d.priceMagnifier} | {len(det)} months")
            else:
                print(f"  --   {sym:7s} {exch:9s} {cur}")
        try:
            m = ib.reqMatchingSymbols(KEYWORDS[s])
            hits = [f"{x.contract.symbol}@{x.contract.primaryExchange}({x.contract.secType})"
                    for x in m if "FUT" in (x.derivativeSecTypes or []) or x.contract.secType == "FUT"][:8]
            if hits:
                print(f"  search '{KEYWORDS[s]}': " + ", ".join(hits))
        except Exception:
            pass
    ib.disconnect()


if __name__ == "__main__":
    main()
