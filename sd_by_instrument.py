#!/usr/bin/env python3
"""Per instrument exploration and validation numbers for the log derived S&D config,
read from the saved trade table of the last research_sd.py run (no rerun, no holdout).

Usage (repo folder):  python3 sd_by_instrument.py [--tf 5] [--cfg key=value ...]
  e.g. python3 sd_by_instrument.py --tf 5 --cfg approach=2.5 fresh=0
"""
import os, sys, itertools
import numpy as np
import research_sd as R

OUT = "research"


def main():
    args = sys.argv[1:]
    tf = int(args[args.index("--tf") + 1]) if "--tf" in args else 5
    cfg = dict(R.STATED)
    if "--cfg" in args:
        for a in args[args.index("--cfg") + 1:]:
            if a.startswith("--"): break
            k, v = a.split("="); cfg[k] = type(R.STATED[k])(v) if not isinstance(R.STATED[k], str) else v
    z = np.load(os.path.join(OUT, f"sd_trades_{tf}m.npz"), allow_pickle=True)
    D = z["D"]; cols = list(z["cols"]); syms = list(z["syms"]); grid = [tuple(float(x) for x in g) for g in z["grid"]]
    R.I.clear(); R.I.update({c: k for k, c in enumerate(cols)}); I = R.I
    age_cap = 2 * R.SESSION_MIN / tf
    tup = (cfg["spike"], cfg["cons"], cfg["approach"], cfg["manage"], cfg["target"], cfg["fresh"], cfg["age"], cfg["bias"], cfg["parabolic"], cfg["session"])
    m, r, rf, why, ov = R.select(D, tup, grid, age_cap)
    year = D[:, I["year"]]; mcode = D[:, I["mcode"]]
    ex, va = m & (year < R.EXPL_END), m & (year >= R.EXPL_END) & (year < R.VAL_END)
    print(f"{tf}m, config {cfg}\n")
    print(f"{'instrument':10s} {'explore n':>9s} {'avgR':>8s} {'t':>6s} {'flat':>8s} {'validate n':>10s} {'avgR':>8s} {'flat':>8s}")
    for k, sym in enumerate(syms + ["ALL"]):
        s = np.ones(len(D), bool) if sym == "ALL" else D[:, I["sym"]] == k
        e, v = ex & s, va & s
        a = R.stats(r[e], mcode[e]); af = R.stats(rf[e], mcode[e]); b = R.stats(r[v], mcode[v]); bf = R.stats(rf[v], mcode[v])
        if a["n"] or b["n"]:
            print(f"{sym:10s} {a['n']:9d} {a['m']:+8.4f} {a['t']:6.2f} {af['m']:+8.4f} {b['n']:10d} {b['m']:+8.4f} {bf['m']:+8.4f}")
    print("\nHoldout stays sealed here; the gate in research_sd.py decides when it is read.")


if __name__ == "__main__":
    main()
