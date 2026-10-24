#!/usr/bin/env python3
"""Stop cap and stop fraction: keep every engine entry, but place the initial stop
either no further than k ATR from the entry (cap_k: min(engine distance, k * ATR))
or at f times the engine's distance (frac_f, f in 0.5 to 2.0). The rest of the exit is the engine's (BE at +1R on the NEW R, 21 EMA phase, parabolic,
200 EMA tightening). Compared with the stop size RULE (skip the trade when the
engine stop is further than 2.5 ATR), which is what v3 candidate 1 tests.

Two ways to score, both reported because they answer different questions:
  R per trade      on the capped R: what risk sized trading earns per unit risked
  ATR per trade    (R * stop distance / ATR): what one contract earns, so the
                   tighter stop is not credited just for a smaller denominator

Preregistered: the cap or fraction with the best R per trade on 2008 to 2016 is tested on
2017 to 2026 against the engine, paired by entry, quarter block bootstrap, one
sided z 1.64. The ATR view and every other k are reported for reference only.
The harness is research_exits.py's: same harvest, same one position per
instrument sequencing (a tighter stop exits earlier, so later entries change).

Usage (repo folder):  python3 research_stopcap.py DATA_DIR [--symbols GC ES ...]
Writes research/stopcap_report.md and research/stopcap_trades.csv.
"""
import os, sys, csv
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

from backtest_hull import load_series
from batch_backtest import build_catalog, iso
from instruments import TICKS
from ib_contracts import UNIVERSE
from research_exits import harvest, exit_engine, quarter, block_t, summarize, MINSPAN, MAXSPAN, WARMUP_DAYS

OUT = "research"; CAPS = [1.0, 1.5, 2.0, 2.5, 3.0]; FRACS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.25, 1.5, 2.0]; RULE = 2.5; Z = 1.64
VARIANTS = ["engine", "rule_2.5"] + [f"cap_{k}" for k in CAPS] + [f"frac_{f}" for f in FRACS]


def capped(s, A, k):
    """Copy of signal s with the stop no further than k ATR from entry."""
    a = A[s["t0"]]; dist = abs(s["entry"] - s["stop0"])
    if a <= 0 or dist <= k * a: return dict(s)
    s2 = dict(s); s2["stop0"] = s["entry"] - s["dir"] * k * a; return s2


def fraction(s, f):
    """Copy of signal s with the stop at f times the engine's stop distance."""
    s2 = dict(s); s2["stop0"] = s["entry"] - s["dir"] * f * abs(s["entry"] - s["stop0"]); return s2


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    syms = list(UNIVERSE)
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    cat = build_catalog(args[0]); os.makedirs(OUT, exist_ok=True)
    rows = []
    for s in syms:
        if s not in cat: print(f"{s:5s} missing"); continue
        tick = TICKS.get(s, 0.0)
        T = load_series(cat[s])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(cat[s], start_ts=start_ts, fill="intrabar"); A = D["A"]
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        bars = sorted(by_bar)
        for name in VARIANTS:
            busy, taken = -1, set()
            for t in bars:
                if t < busy: continue
                for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                    if sg["edge"] in taken: continue
                    a = A[t] if A[t] > 0 else 1e-12; dist0 = abs(sg["entry"] - sg["stop0"])
                    if name == "rule_2.5" and dist0 > RULE * a: continue   # the rule skips; the line stays untraded
                    taken.add(sg["edge"])
                    s2 = capped(sg, A, float(name.split("_")[1])) if name.startswith("cap") else fraction(sg, float(name.split("_")[1])) if name.startswith("frac") else dict(sg)
                    ei, ex, why, mfe = exit_engine(D, s2)
                    R = abs(s2["entry"] - s2["stop0"]); r = (ex - s2["entry"]) / R * s2["dir"]
                    cost = (2.0 * tick) / R if tick else 0.0
                    rows.append(dict(symbol=s, variant=name, entry_time=iso(D["T"][t]), t0=t, dir=sg["dir"], quarter=quarter(D["T"][t]),
                                     year=datetime.fromtimestamp(int(D["T"][t]), timezone.utc).year, stop_atr0=round(dist0 / a, 3),
                                     stop_atr=round(R / a, 3), capped=int(R < dist0 - 1e-9), R=round(r - cost, 6), atr=round((r - cost) * R / a, 6), why=why))
                    busy = ei; break
        print(f"{s:5s} " + ", ".join(f"{v} {sum(1 for r in rows if r['symbol'] == s and r['variant'] == v)}" for v in VARIANTS), flush=True)
    with open(os.path.join(OUT, "stopcap_trades.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    def paired(va, vb, cond):
        ka = {(r["symbol"], r["t0"]): r for r in rows if r["variant"] == va and cond(r)}
        kb = {(r["symbol"], r["t0"]): r for r in rows if r["variant"] == vb and cond(r)}
        keys = [k for k in ka if k in kb]
        dR, dA = block_t([kb[k]["R"] - ka[k]["R"] for k in keys], [ka[k]["quarter"] for k in keys]), block_t([kb[k]["atr"] - ka[k]["atr"] for k in keys], [ka[k]["quarter"] for k in keys])
        return len(keys), dR, dA

    periods = (("explore 2008-2016", lambda r: r["year"] < 2017), ("holdout 2017-2026", lambda r: r["year"] >= 2017))
    L = ["# Stop cap vs stop size rule vs engine (engine entries, engine exit logic on the capped R)\n",
         "R = per trade on each variant's own stop (risk sized view); ATR = per contract view. Paired = same entries only; "
         "a cap changes the sequence of later entries, so the unpaired rows differ in trade count too.\n",
         "| set | variant | trades | capped | avgR | win% | PF | boot t (R) | avg ATR | boot t (ATR) | paired n | dR vs engine | t | dATR vs engine | t |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    best = None
    for pname, cond in periods:
        for v in VARIANTS:
            sub = [r for r in rows if r["variant"] == v and cond(r)]
            if not sub: continue
            sm = summarize([r["R"] for r in sub]); _, tR = block_t([r["R"] for r in sub], [r["quarter"] for r in sub])
            mA, tA = block_t([r["atr"] for r in sub], [r["quarter"] for r in sub])
            cap = sum(r["capped"] for r in sub)
            if v == "engine":
                L.append(f"| {pname} | engine | {sm['n']} | | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {tR:.2f} | {mA:+.4f} | {tA:.2f} | | | | | |")
                continue
            n, (dR, tdR), (dA, tdA) = paired("engine", v, cond)
            L.append(f"| {pname} | {v} | {sm['n']} | {cap} | {sm['avgR']:+.4f} | {sm['win']:.1f} | {sm['PF']:.2f} | {tR:.2f} | {mA:+.4f} | {tA:.2f} | {n} | {dR:+.4f} | {tdR:.2f} | {dA:+.4f} | {tdA:.2f} |")
            if pname.startswith("explore") and v != "engine" and v != "rule_2.5" and (best is None or sm["avgR"] > best[1]): best = (v, sm["avgR"])
    if best:
        n, (dR, tdR), (dA, tdA) = paired("engine", best[0], periods[1][1])
        L += [f"\n## Preregistered test\n", f"Best cap or fraction on exploration by avgR: **{best[0]}** ({best[1]:+.4f}).",
              f"Holdout, {best[0]} minus engine, paired by entry: **{dR:+.4f} R per trade, t {tdR:.2f} -> {'PASS' if tdR > Z else 'no'}** (z {Z}). "
              f"Per contract view: {dA:+.4f} ATR, t {tdA:.2f}.",
              "\nA PASS in R with a negative ATR number means the cap only helps when sizing by risk (more contracts on the tighter stop), "
              "which is what live sizing will do; it does not help one contract per trade."]
    open(os.path.join(OUT, "stopcap_report.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}/stopcap_report.md")


if __name__ == "__main__":
    main()
