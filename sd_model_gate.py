#!/usr/bin/env python3
"""The selection model from sd_discriminate.py (fitted on Adam's 2026 log window) applied to
every engine rejection event on the exploration and validation years. No holdout is read.

For each event: features at the rejection bar, model score, mechanical outcome (fixed stop
3R target and BE 2R, from sd_replay.replay). Report, per set (explore 2008 to 2014, validate
2015 to 2016): mean R for all events, the top half, top quarter and top tenth by score, with a
monthly block bootstrap t for the top quarter, and the same by session. Gate: the top quarter
positive on both sets with t > 2 on exploration means the holdout may be read next, with the
position gated engine, not here.

Usage (repo folder):  python3 sd_model_gate.py DATA_DIR_1m [--symbols NQ ES ...]
Writes research/sd_model_gate.md and research/sd_model_events_<SYM>.csv.
"""
import os, sys, csv, glob, re, json, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

import research_sd as R
from research_sd import load_1m
from sd_discriminate import build_B, features, FEATS
from sd_replay import replay

OUT = "research"; EXPL_END, VAL_END = 2015, 2017


def block_t(vals, months, reps=300, seed=5):
    by = defaultdict(list)
    for v, m in zip(vals, months): by[m].append(v)
    keys = list(by); rng = np.random.default_rng(seed)
    sums = np.array([sum(by[k]) for k in keys]); cnt = np.array([len(by[k]) for k in keys], float)
    picks = rng.integers(0, len(keys), (reps, len(keys))); means = sums[picks].sum(1) / cnt[picks].sum(1)
    m = float(np.mean(vals)); sd = float(means.std()); return m, (m / sd if sd > 0 else float("nan"))


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    syms = ["NQ"]
    if "--symbols" in args:
        syms = []
        for a in args[args.index("--symbols") + 1:]:
            if a.startswith("--"): break
            syms.append(a)
    model = json.load(open(os.path.join(OUT, "sd_model.json"))); mu, sd, w = np.array(model["mu"]), np.array(model["sd"]), np.array(model["w"])
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    cfg = R.STATED; L = [f"# Selection model on exploration and validation years (model fitted on {model['window'][0]} to {model['window'][1]}, NQ log)\n",
                         "Events are every engine rejection (no position gating), scored by the logistic model from sd_discriminate.py; outcome is the mechanical "
                         "fixed stop 3R replay. Holdout 2017 onward is not read here.\n"]
    for sym in syms:
        t0 = time.time(); raw = load_1m(cat[sym]); end = int(datetime(VAL_END, 1, 1, tzinfo=timezone.utc).timestamp()); keep = raw[0] < end; raw = tuple(x[keep] for x in raw)
        B = build_B(raw); T, O, H, L_, C, A = B[:6]; mod = B[13]; sess = (T - 60 + 6 * 3600) // 86400; V = R.resample(*raw, 5)[5]
        tick = R.TICKS.get(sym, 0.25); mult = R.MICROS[sym][1]
        sig = R.scan_signals((T, O, H, L_, C, V), cfg["spike"], cfg["cons"], cfg["approach"], tick)
        rows = []
        for s in sig:
            f = features(s["j"], s["dir"], s["lo"], s["hi"], s, B); out = replay(s["j"], s["dir"], s["hi"], s["lo"], T, O, H, L_, C, A, mod, sess, None, tick, mult)
            if out is None: continue
            x = np.array([f[k] for k in FEATS]); z = (x - mu) / sd; score = 1 / (1 + np.exp(-(w[0] + z @ w[1:])))
            dt = datetime.fromtimestamp(int(T[s["j"]]), timezone.utc)
            rows.append(dict(time=dt.strftime("%Y-%m-%d %H:%M"), year=dt.year, month=dt.strftime("%Y-%m"), dir=s["dir"], score=round(float(score), 4),
                             fixed_3R=round(out["fixed_3R"], 3), be_2R=round(out["be_2R"], 3), hour=int(mod[s["j"]] // 60)))
        with open(os.path.join(OUT, f"sd_model_events_{sym}.csv"), "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
        print(f"{sym}: {len(rows)} events through {VAL_END - 1} ({time.time() - t0:.0f}s)", flush=True)
        L += [f"\n## {sym}\n", "| set | events | all fixed_3R | top half | top quarter | top quarter t | top tenth | all be_2R | top quarter be_2R |", "|---|---|---|---|---|---|---|---|---|"]
        sc = np.array([r["score"] for r in rows]); yr = np.array([r["year"] for r in rows]); r3 = np.array([r["fixed_3R"] for r in rows]); b2 = np.array([r["be_2R"] for r in rows])
        mo = [r["month"] for r in rows]; gate = []
        for name, m in (("explore", yr < EXPL_END), ("validate", (yr >= EXPL_END) & (yr < VAL_END))):
            if m.sum() < 50: continue
            q50, q75, q90 = np.quantile(sc[m], [0.5, 0.75, 0.9]); top = m & (sc >= q75)
            mt, tt = block_t(r3[top], [x for x, k in zip(mo, top) if k]); gate.append((mt, tt))
            L.append(f"| {name} | {m.sum()} | {r3[m].mean():+.4f} | {r3[m & (sc >= q50)].mean():+.4f} | {mt:+.4f} | {tt:.2f} | {r3[m & (sc >= q90)].mean():+.4f} | "
                     f"{b2[m].mean():+.4f} | {b2[top].mean():+.4f} |")
        hr = np.array([r["hour"] for r in rows]); ex = yr < EXPL_END
        sessions = {"Asia 18-03": (hr >= 18) | (hr < 3), "London 03-07": (hr >= 3) & (hr < 7), "NY AM 07-12": (hr >= 7) & (hr < 12), "NY PM 12-17": (hr >= 12) & (hr < 17)}
        L.append("\nExploration by session, all events vs top quarter by score: " + "; ".join(
            f"{k}: {r3[ex & v].mean():+.3f} (n={(ex & v).sum()}) vs {r3[ex & v & (sc >= np.quantile(sc[ex], 0.75))].mean():+.3f} (n={(ex & v & (sc >= np.quantile(sc[ex], 0.75))).sum()})"
            for k, v in sessions.items() if (ex & v).sum() > 20))
        ok = len(gate) == 2 and gate[0][0] > 0 and gate[1][0] > 0 and gate[0][1] > 2
        L.append(f"\n**Gate for {sym}: {'OPEN, the holdout may be read with the position gated engine' if ok else 'shut'}** (top quarter explore {gate[0][0]:+.4f} t {gate[0][1]:.2f}; validate {gate[1][0]:+.4f})" if len(gate) == 2 else "\nnot enough events")
    open(os.path.join(OUT, "sd_model_gate.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L)); print(f"\n-> {OUT}/sd_model_gate.md")


if __name__ == "__main__":
    main()
