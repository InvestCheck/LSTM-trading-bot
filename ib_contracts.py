"""IBKR contract mapping for the 70 instrument frozen universe.

Each FirstRateData symbol maps to how IBKR identifies the product, which
contract months are traded, and whether the product is physically delivered
with notice before the contract month (which pulls the roll date earlier).

EVERY ROW IS UNVERIFIED until verify_contracts.py reports it OK. IBKR symbols
for Eurex, Euronext, ICE and some CME products differ from exchange codes, and
a wrong row fails loudly there rather than silently trading the wrong thing.

Roll rule (forward_test_protocol.md): roll at the close of the session
ROLL_DAYS trading days before the earlier of first notice day and last trade
date. IBKR's API does not publish first notice day, so for physically
delivered products it is proxied by the last weekday of the month before the
contract month, which is the first notice day for metals, grains and
Treasuries and slightly conservative elsewhere.
"""
from datetime import date, timedelta

ROLL_DAYS = 5

UNIVERSE = """A6 AD B B6 BZ CL CNH CT DC DX E1 E6 E7 ES EW FBON FBTP FCE FDAX
FDXM FESX FGBL FGBM FGBX FOAT FTI FTUK FXXP G GC GF HE HG HO J1 J7 KE LE MFS MGC
MME MP N6 NG NIY NKD NOK NQ PA PL RB RP RS RTY RY SB SEK SI SIR TN UB XC YM ZC ZF
ZL ZM ZN ZS ZT""".split()

Q = "HMUZ"          # quarterly cycle
ALL = "FGHJKMNQUVXZ"

def _c(symbol, exchange, currency="USD", months=Q, physical=False, tradingClass=""):
    return dict(symbol=symbol, exchange=exchange, currency=currency,
                months=months, physical=physical, tradingClass=tradingClass)

IB = {
    # CME FX
    "A6":  _c("AUD", "CME"),
    "AD":  _c("CAD", "CME"),          # instruments.py calls AD the Canadian dollar
    "B6":  _c("GBP", "CME"),
    "CNH": _c("CNH", "CME", "CNH"),      # USD/CNH is quoted in CNH
    "E1":  _c("CHF", "CME"),
    "E6":  _c("EUR", "CME"),
    "E7":  _c("E7",  "CME"),
    "J1":  _c("JPY", "CME"),
    "J7":  _c("J7",  "CME"),
    "MP":  _c("6M",  "CME"),             # IBKR's MXP is Micro XRP; the peso is 6M
    "N6":  _c("NZD", "CME"),
    "NOK": _c("NOK", "CME"),
    "SEK": _c("SEK", "CME"),
    "RP":  _c("RP",  "CME", "GBP"),      # EUR/GBP is quoted in GBP
    "RY":  _c("RY",  "CME", "JPY"),      # EUR/JPY is quoted in JPY
    "SIR": _c("SIR", "CME"),
    # CME equity index
    "ES":  _c("ES",  "CME"),
    "NQ":  _c("NQ",  "CME"),
    "RTY": _c("RTY", "CME"),
    "EW":  _c("EMD", "CME"),
    "NIY": _c("NIY", "CME", "JPY", tradingClass="NIY"),   # symbol also lists the ENY mini
    "NKD": _c("NKD", "CME", tradingClass="NKD"),
    # CME livestock and dairy
    "GF":  _c("GF",  "CME", months="FHJKQUVX"),
    "HE":  _c("HE",  "CME", months="GJKMNQVZ"),
    "LE":  _c("LE",  "CME", months="GJMQVZ", physical=True),
    "DC":  _c("DA",  "CME", months=ALL, tradingClass="DC"),   # Class III milk is symbol DA at IBKR
    # CBOT
    "YM":  _c("YM",  "CBOT"),
    "ZT":  _c("ZT",  "CBOT", physical=True),
    "ZF":  _c("ZF",  "CBOT", physical=True),
    "ZN":  _c("ZN",  "CBOT", physical=True),
    "TN":  _c("TN",  "CBOT", physical=True),
    "UB":  _c("UB",  "CBOT", physical=True),
    "ZC":  _c("ZC",  "CBOT", months="HKNUZ", physical=True),
    "XC":  _c("YC",  "CBOT", months="HKNUZ", physical=True),   # CBOT mini corn is YC at IBKR
    "ZS":  _c("ZS",  "CBOT", months="FHKNQUX", physical=True),
    "ZL":  _c("ZL",  "CBOT", months="FHKNQUVZ", physical=True),
    "ZM":  _c("ZM",  "CBOT", months="FHKNQUVZ", physical=True),
    "KE":  _c("KE",  "CBOT", months="HKNUZ", physical=True),
    # NYMEX
    "CL":  _c("CL",  "NYMEX", months=ALL, physical=True),
    "BZ":  _c("BZ",  "NYMEX", months=ALL),
    "HO":  _c("HO",  "NYMEX", months=ALL, physical=True),
    "RB":  _c("RB",  "NYMEX", months=ALL, physical=True),
    "NG":  _c("NG",  "NYMEX", months=ALL, physical=True),
    "PA":  _c("PA",  "NYMEX", physical=True),
    "PL":  _c("PL",  "NYMEX", months="FJNV", physical=True),
    # COMEX
    "GC":  _c("GC",  "COMEX", months="GJMQVZ", physical=True),
    "MGC": _c("MGC", "COMEX", months="GJMQVZ", physical=True),
    "SI":  _c("SI",  "COMEX", months="HKNUZ", physical=True, tradingClass="SI"),   # symbol SI also returns the SIL micro
    "HG":  _c("HG",  "COMEX", months="HKNUZ", physical=True),
    # ICE US (IBKR exchange code NYBOT)
    "CT":  _c("CT",  "NYBOT", months="HKNVZ", physical=True),
    "SB":  _c("SB",  "NYBOT", months="HKNV", physical=True),
    "RS":  _c("RS",  "NYBOT", "CAD", months="FHKNX", physical=True),
    "DX":  _c("DX",  "NYBOT"),
    "MFS": _c("MFS", "NYBOT"),
    "MME": _c("MME", "NYBOT"),
    # Eurex
    "FDAX": _c("DAX",    "EUREX", "EUR", tradingClass="FDAX"),
    "FDXM": _c("DAX",    "EUREX", "EUR", tradingClass="FDXM"),
    "FESX": _c("ESTX50", "EUREX", "EUR", tradingClass="FESX"),
    "FXXP": _c("SXXP",   "EUREX", "EUR", tradingClass="FXXP"),
    "FGBL": _c("GBL",    "EUREX", "EUR", tradingClass="FGBL"),
    "FGBM": _c("GBM",    "EUREX", "EUR", tradingClass="FGBM"),
    "FGBX": _c("GBX",    "EUREX", "EUR", tradingClass="FGBX"),
    "FOAT": _c("OAT",    "EUREX", "EUR", tradingClass="FOAT"),
    "FBTP": _c("BTP",    "EUREX", "EUR", tradingClass="FBTP"),
    "FBON": _c("BONO",   "EUREX", "EUR", tradingClass="FBON"),
    # Euronext and ICE Europe
    "FCE":  _c("CAC40", "MONEP", "EUR", months=ALL, tradingClass="FCE"),   # symbol also lists the MFC mini
    "FTI":  _c("EOE",   "FTA",   "EUR", months=ALL, tradingClass="FTI"),   # symbol also lists the MFA mini
    "FTUK": _c("Z",     "ICEEU", "GBP"),
    "B":    _c("COIL",  "IPE",   "USD", months=ALL),   # ICE Brent lives on IBKR's IPE exchange code
    "G":    _c("R",     "ICEEU", "GBP", physical=True),
}

assert sorted(IB) == sorted(UNIVERSE), set(IB) ^ set(UNIVERSE)

MONTH_CODE = {c: i + 1 for i, c in enumerate("FGHJKMNQUVXZ")}


def _weekday_before(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def roll_date(last_trade, contract_month, physical):
    """Date whose session close triggers the roll. last_trade is a date,
    contract_month is 'YYYYMM'."""
    end = last_trade
    if physical:
        first = date(int(contract_month[:4]), int(contract_month[4:6]), 1)
        end = min(end, _weekday_before(first))
    d = end
    for _ in range(ROLL_DAYS):
        d = _weekday_before(d)
    return d


def month_letter(contract_month):
    return "FGHJKMNQUVXZ"[int(contract_month[4:6]) - 1]


def contract_rows(details, spec):
    """reqContractDetails results -> [(last_trade, roll_date, ContractDetails)]
    for the traded months only, sorted by last trade date."""
    def mult(d):
        try: return float(d.contract.multiplier)
        except (TypeError, ValueError): return 0.0
    if spec["tradingClass"]:
        details = [d for d in details if d.contract.tradingClass == spec["tradingClass"]]
    elif details:
        # IBKR lists minis under the same symbol: keep the full size trading class
        best = max({d.contract.tradingClass for d in details},
                   key=lambda tc: max(mult(d) for d in details if d.contract.tradingClass == tc))
        details = [d for d in details if d.contract.tradingClass == best]
    rows = []
    for d in details:
        cm = (d.contractMonth or d.contract.lastTradeDateOrContractMonth)[:6]
        if len(cm) != 6 or month_letter(cm) not in spec["months"]:
            continue
        ltd_s = d.contract.lastTradeDateOrContractMonth
        if len(ltd_s) < 8:
            continue
        ltd = date(int(ltd_s[:4]), int(ltd_s[4:6]), int(ltd_s[6:8]))
        rows.append((ltd, roll_date(ltd, cm, spec["physical"]), d))
    rows.sort(key=lambda r: r[0])
    return rows


def pick_active(details, spec, today):
    """The contract the protocol trades today: the earliest traded month whose
    roll date is still ahead. Returns (ContractDetails, roll_date) or (None, None)."""
    for ltd, rd, d in contract_rows(details, spec):
        if rd > today:
            return d, rd
    return None, None
