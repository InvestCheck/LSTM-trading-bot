#!/usr/bin/env python3
"""Commissions and tick values, for converting dollar costs into R.

Cost in R is `commission_round_trip / (R_ticks * tick_value)`, so this needs two
things the rest of the repo does not have: the dollar value of one tick, and the
all-in round-trip cost per contract.

WHY THIS FILE IS DELIBERATELY INCOMPLETE
----------------------------------------
Populating 103 tick values from memory is how bias source 3 happened. That table
was wrong because entries were assumed rather than checked, and FirstRateData
reuses tickers that mean something else elsewhere (`AD` is Canadian Dollar here,
not Australian; `C` is London Cocoa, not Corn). So this file carries only
contracts whose specification is unambiguous, and everything else raises rather
than silently returning a default.

`cost_in_R()` raises KeyError on an unknown symbol. It does NOT return 0.0. A
zero default is what made 118 of 131 instruments silently report pre-cost
results while appearing to be a costed run.

FILL IN THE REST FROM PRIMARY SOURCES
-------------------------------------
Tick values: the CME/ICE/Eurex contract specification page for each product.
Commissions: IBKR's futures commission page, with the "Exchange Fees" and
"Regulatory Fees" sections EXPANDED. The headline per-contract number is IBKR's
own cut only and is roughly a third of the true cost on standard CME contracts.

Verify against a real fill from an account statement before trusting any of it.
"""

# ---------------------------------------------------------------- tick values
# USD per one minimum tick. tick_value = tick_size * contract_multiplier.
# Every entry below is a contract whose spec is unambiguous. If you are not
# certain, leave it out; an absent symbol raises, a wrong one lies.
TICK_VALUE = {
    # COMEX / NYMEX metals
    "GC": 10.00,     # Gold, 100 oz, 0.10 tick
    "MGC": 1.00,     # Micro Gold, 10 oz, 0.10 tick
    "SI": 25.00,     # Silver, 5000 oz, 0.005 tick
    "HG": 12.50,     # Copper, 25000 lb, 0.0005 tick
    "PL": 5.00,      # Platinum, 50 oz, 0.10 tick
    "PA": 5.00,      # Palladium, 100 oz, 0.05 tick

    # NYMEX energy
    "CL": 10.00,     # WTI Crude, 1000 bbl, 0.01 tick
    "MCL": 1.00,     # Micro WTI, 100 bbl, 0.01 tick
    "NG": 10.00,     # Natural Gas, 10000 MMBtu, 0.001 tick
    "RB": 4.20,      # RBOB Gasoline, 42000 gal, 0.0001 tick
    "HO": 4.20,      # Heating Oil, 42000 gal, 0.0001 tick

    # CME equity index
    "ES": 12.50,     # E-mini S&P 500, 0.25 tick
    "MES": 1.25,     # Micro E-mini S&P 500
    "NQ": 5.00,      # E-mini Nasdaq 100, 0.25 tick
    "MNQ": 0.50,     # Micro E-mini Nasdaq 100
    "RTY": 5.00,     # E-mini Russell 2000, 0.10 tick
    "M2K": 0.50,     # Micro E-mini Russell 2000
    "YM": 5.00,      # E-mini Dow, 1 pt tick

    # CBOT rates
    "ZN": 15.625,    # 10Y Note, 1/64 tick
    "TN": 15.625,    # Ultra 10Y Note, 1/64 tick
    "ZF": 7.8125,    # 5Y Note, 1/128 tick
    "US": 31.25,     # 30Y Bond, 1/32 tick
    "UB": 31.25,     # Ultra Bond, 1/32 tick

    # CBOT grains and oilseeds
    "ZC": 12.50,     # Corn, 5000 bu, 1/4 cent tick
    "ZS": 12.50,     # Soybeans, 5000 bu, 1/4 cent tick
    "ZW": 12.50,     # Chicago Wheat, 5000 bu, 1/4 cent tick
    "ZO": 12.50,     # Oats, 5000 bu, 1/4 cent tick
    "KE": 12.50,     # KC Wheat, 5000 bu, 1/4 cent tick
    "ZM": 10.00,     # Soybean Meal, 100 short tons, 0.10 tick
    "ZL": 6.00,      # Soybean Oil, 60000 lb, 0.01 tick

    # CME livestock
    "LE": 10.00,     # Live Cattle, 40000 lb, 0.00025 tick
    "HE": 10.00,     # Lean Hogs, 40000 lb, 0.00025 tick
    "GF": 12.50,     # Feeder Cattle, 50000 lb, 0.00025 tick

    # CME FX
    "E6": 6.25,      # EUR/USD, 125000 EUR, 0.00005 tick
    "E7": 6.25,      # E-mini EUR/USD, 62500 EUR, 0.0001 tick
    "B6": 6.25,      # GBP/USD, 62500 GBP, 0.0001 tick
    "A6": 5.00,      # AUD/USD, 100000 AUD, 0.00005 tick
    "N6": 10.00,     # NZD/USD, 100000 NZD, 0.0001 tick

    # CME crypto
    "MBT": 0.50,     # Micro Bitcoin, 0.1 BTC, 5.00 tick
    "MET": 0.50,     # Micro Ether, 0.1 ETH, 5.00 tick
}

# Symbols in the scan whose tick value has NOT been verified. Listed explicitly
# so the gap is visible rather than inferred from absence. Anything here is
# excluded from costed results until filled in from the contract spec.
UNVERIFIED_TICK_VALUE = {
    # CME FX, ambiguous contract size in this data source
    "J7", "J1", "AD", "T6", "SEK", "NOK", "CNH", "RP", "RY", "MP", "PJY", "DX",
    # Eurex
    "FGBL", "FGBM", "FGBS", "FGBX", "FDAX", "FDXM", "FDXS", "FESX", "FBTP",
    "FBTS", "FBON", "FOAT", "FSMX", "FVSA", "FMWO", "FEU3", "FDIV",
    # ICE / Euronext / other non-US
    "B", "G", "BZ", "C", "CC", "CT", "KC", "SB", "OJ", "EBM", "RM", "FCE",
    "FTUK", "FTDX", "FXXP", "FTI", "L", "SO3", "JB", "NIY", "NKD",
    # STIR (excluded on cost grounds anyway)
    "ZQ", "ER", "SR1", "SR3", "ZT",
    # everything else in instruments.py not named above
}

# --------------------------------------------------------------- commissions
# All-in ROUND TRIP cost per contract in USD: IBKR commission + exchange fee +
# regulatory fee, both sides.
#
# ESTIMATED, NOT VERIFIED. IBKR's published per-contract figure is their own
# commission only; the exchange and regulatory components sit in collapsed
# sections on that page and are the larger share. These use IBKR Tiered at the
# <=1000 contracts/month band plus a CME non-member exchange fee estimate.
# Replace with figures from an actual account statement before publishing
# anything that depends on them.
COMMISSION_RT = {
    "standard": 4.64,   # IBKR 0.85 + exch ~1.45 + NFA 0.02, per side, x2
    "micro": 1.24,      # IBKR 0.25 + exch ~0.35 + NFA 0.02, per side, x2
    "fx_mini": 3.04,    # IBKR 0.50 + exch ~1.00 + NFA 0.02, per side, x2
    "fx_micro": 1.04,   # IBKR 0.15 + exch ~0.35 + NFA 0.02, per side, x2
}

# IBKR's micro/spot-quoted band, taken verbatim from their published list.
MICRO = {"MES", "MNQ", "M2K", "VOLQ", "MYM", "2YY", "5YY", "10Y", "30Y", "MCL",
         "MRB", "MGC", "MWN", "MTN", "SIL", "VXM", "MHNG", "MHO", "MNK", "MNI",
         "MZC", "MZS", "MZW", "MZL", "MZM", "QBTC", "QDOW", "QETH", "QNDX",
         "QRTY", "QSPX", "SIC", "MBT", "MET"}
FX_MINI = {"E7", "J7", "B7", "A7"}
FX_MICRO = {"M6E", "M6A", "M6B", "MJY", "MCD", "MSF"}


def commission_rt(symbol):
    """All-in round-trip cost in USD for one contract."""
    if symbol in MICRO:
        return COMMISSION_RT["micro"]
    if symbol in FX_MICRO:
        return COMMISSION_RT["fx_micro"]
    if symbol in FX_MINI:
        return COMMISSION_RT["fx_mini"]
    return COMMISSION_RT["standard"]


def cost_in_R(symbol, r_ticks):
    """Commission as a fraction of one R.

    Raises KeyError if the tick value is unverified. That is deliberate: a zero
    default is how 118 of 131 instruments silently reported pre-cost results.
    """
    tv = TICK_VALUE.get(symbol)
    if tv is None:
        raise KeyError(
            f"no verified tick value for {symbol!r}. Add it from the contract "
            f"specification, or exclude the symbol. Do not guess.")
    bet_usd = r_ticks * tv
    if bet_usd <= 0:
        raise ValueError(f"{symbol}: non-positive bet size")
    return commission_rt(symbol) / bet_usd


def covered():
    return set(TICK_VALUE)


if __name__ == "__main__":
    print(f"{len(TICK_VALUE)} verified tick values, "
          f"{len(UNVERIFIED_TICK_VALUE)} known gaps\n")
    print(f"{'symbol':8s} {'tick $':>8s} {'comm RT':>8s} "
          f"{'bet @64t':>10s} {'comm as % of R':>15s}")
    print("-" * 54)
    for s in sorted(TICK_VALUE):
        tv = TICK_VALUE[s]
        bet = 64 * tv
        print(f"{s:8s} {tv:8.3f} {commission_rt(s):8.2f} {bet:10.2f} "
              f"{cost_in_R(s, 64):15.1%}")
    print("-" * 54)
    print("'bet @64t' uses the median stop of 64 ticks from the span sweep.")
