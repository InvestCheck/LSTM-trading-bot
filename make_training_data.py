#!/usr/bin/env python3
"""Build the tier-model training set from seed/*.csv.

Pools all metals trades, attaches SIGNAL TIME features and the OUTCOME label,
sorts chronologically, and splits by time (default: first 70% train, last 30%
test). Writes tier_data/training_data.csv (with a split column) plus train.csv
and test.csv.

HARD LEAKAGE RULE: FEATURE_COLS are all known at the moment of entry. LABEL_COLS
are outcomes, known only after the trade closes. Train ONLY on FEATURE_COLS.
Never feed a LABEL_COL (or anything derived from it) to the model.

Usage:
  python3 make_training_data.py                 default metals (MGC PL PA SI HG)
  python3 make_training_data.py MGC PL HG       a subset
"""
import os, sys, csv
from datetime import datetime, timezone
from backtest_hull import run, load_series

SEED_DIR = "seed"
OUT = "tier_data"
MAXSPAN = 10**90      # effectively unbounded (no line is ever this old); same effect as 10**9
WARMUP_DAYS = 60
TEST_FRAC = 0.30                       # last 30% by time is the holdout
METALS = ["MGC", "PL", "PA", "SI", "HG"]

FEATURE_COLS = ["symbol", "dir", "kind", "stop_src", "touches", "span_bars",
                "R_pct", "slope_pct", "entry_hour", "entry_dow"]
LABEL_COLS = ["R_realized", "win"]     # outcomes, target only, never inputs
META_COLS = ["entry_time", "entry_ts"]  # bookkeeping, not a feature


def iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M")


def rows_for(sym, path):
    T, O, H, L, C = load_series(path)
    st = int(T.min()) + WARMUP_DAYS * 86400
    _, trades, _, _ = run(sym, path, 1.0, st, CAP=1e12, MAXSPAN=MAXSPAN,
                          causal=True, fill="intrabar")   # leak free features + realistic labels
    out = []
    for tr in trades:
        ets = int(T[tr["t0"]]); entry = tr["entry"]; Rpx = abs(entry - tr["stop0"])
        if Rpx <= 0:
            continue
        dt = datetime.fromtimestamp(ets, timezone.utc)
        touches = len(tr["tch"]) if isinstance(tr.get("tch"), (list, tuple)) else tr.get("tch")
        out.append({
            "entry_time": iso(ets), "entry_ts": ets,
            "symbol": sym, "dir": tr["dir"], "kind": tr["kind"], "stop_src": tr["stop_src"],
            "touches": touches, "span_bars": int(tr["t0"] - tr["a"]),
            "R_pct": round(Rpx / entry, 6), "slope_pct": round(tr["m"] / entry, 8),
            "entry_hour": dt.hour, "entry_dow": dt.weekday(),
            "R_realized": tr["R"], "win": int(tr["R"] > 0),
        })
    return out


def main():
    syms = [a for a in sys.argv[1:] if not a.startswith("-")] or METALS
    rows = []
    for sym in syms:
        path = os.path.join(SEED_DIR, f"{sym}.csv")
        if not os.path.exists(path):
            print(f"  skip {sym}: missing {path}"); continue
        r = rows_for(sym, path); rows += r
        print(f"  {sym}: {len(r)} trades")
    if not rows:
        print("no trades; check seed/*.csv"); return
    rows.sort(key=lambda r: r["entry_ts"])
    cut = int(len(rows) * (1 - TEST_FRAC))
    for i, r in enumerate(rows):
        r["split"] = "train" if i < cut else "test"
    cutdate = rows[cut]["entry_time"][:10]
    os.makedirs(OUT, exist_ok=True)
    cols = META_COLS + FEATURE_COLS + LABEL_COLS + ["split"]

    def write(path, subset):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
            for r in subset:
                w.writerow({k: r[k] for k in cols})

    write(os.path.join(OUT, "training_data.csv"), rows)
    write(os.path.join(OUT, "train.csv"), [r for r in rows if r["split"] == "train"])
    write(os.path.join(OUT, "test.csv"), [r for r in rows if r["split"] == "test"])

    ntr = sum(r["split"] == "train" for r in rows); nte = len(rows) - ntr
    wtr = sum(r["win"] for r in rows if r["split"] == "train") / max(ntr, 1)
    wte = sum(r["win"] for r in rows if r["split"] == "test") / max(nte, 1)
    print(f"\ntotal {len(rows)} trades  ->  train {ntr} (win {wtr:.0%}), test {nte} (win {wte:.0%})")
    print(f"chronological split at {cutdate}  (train before, test after)")
    print(f"features (inputs): {FEATURE_COLS}")
    print(f"labels (target only, NEVER inputs): {LABEL_COLS}")
    print(f"written -> {OUT}/training_data.csv, train.csv, test.csv")


if __name__ == "__main__":
    main()
