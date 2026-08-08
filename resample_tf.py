#!/usr/bin/env python3
"""Resample 1-hour OHLCV files to a higher timeframe (default 4H).

  python3 resample_tf.py seed seed_4h --rule 4h

Reads every .txt/.csv in SRC (FirstRateData or epoch format), aggregates to the
rule with open=first, high=max, low=min, close=last, volume=sum, writes epoch-
stamped CSVs to DST that backtest_hull.load_series reads directly. Symbol names
are preserved.
"""
import sys, os, glob, re
import pandas as pd

def resample_one(src, dst, rule):
    df = pd.read_csv(src, header=None, names=["t","o","h","l","c","v"])
    # time may be datetime string or epoch
    t = pd.to_datetime(df["t"], utc=True, errors="coerce")
    if t.isna().mean() > 0.5:
        t = pd.to_datetime(pd.to_numeric(df["t"], errors="coerce"), unit="s", utc=True)
    df = df.assign(t=t).dropna(subset=["t"]).set_index("t").sort_index()
    agg = (df.resample(rule, label="left", closed="left")
             .agg(o=("o","first"), h=("h","max"), l=("l","min"),
                  c=("c","last"), v=("v","sum")).dropna())
    out = agg.reset_index()
    out["t"] = (out["t"] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
    out[["t","o","h","l","c","v"]].to_csv(dst, header=False, index=False)
    return len(out)

def main():
    src, dst = sys.argv[1], sys.argv[2]
    rule = "4h"
    if "--rule" in sys.argv: rule = sys.argv[sys.argv.index("--rule")+1]
    os.makedirs(dst, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src,"*.txt")) + glob.glob(os.path.join(src,"*.csv")))
    for p in files:
        sym = re.sub(r"(_full_1hour.*|\.(csv|txt))$","", os.path.basename(p))
        n = resample_one(p, os.path.join(dst, sym+".csv"), rule)
        print(f"  {sym}: {n} bars -> {dst}/{sym}.csv")

if __name__ == "__main__":
    main()
