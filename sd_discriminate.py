#!/usr/bin/env python3
"""What separates the S&D rejections Adam takes from the ones the engine fires on and
he skips, measured on the bars at the rejection bar.

Data: every rejection event from research_sd.scan_signals over Adam's log window (the
log derived rules), labelled 1 when it matches one of his logged setups (same direction,
rejection bar within 2 bars, zones overlapping) and 0 otherwise; his setups the engine
never fired on are added as extra positives (features from his reconstructed zone).
Outcome: the mechanical fixed stop 3R replay from sd_replay.py for every event.

Features at the rejection bar, all using bars up to and including it:
  appr_max  max bar range of the 6 bars into the zone / ATR      appr_net  |close 12 bars ago to last close| / ATR
  spike     spike multiple of the zone candle                     cons      6 bar base span before the zone / ATR
  taps, cin wick touches / closes inside since price left         age       bars since the zone was born / 100
  zsize     zone height / ATR                                     rej_pos   where the rejection bar closed in its range (0 low, 1 high), signed
  rej_rng   rejection bar range / ATR                             e21_5, e21_15  close vs 21 EMA on 5m and 15m / ATR, signed by direction
  s21_15    slope of the 15m 21 EMA over 5 bars / ATR, signed     e50_4h    close vs 4h 50 EMA / ATR, signed
  hh_15     net higher highs and higher lows over the last 20 15m swings, signed (structure read)
  vwap      close vs session VWAP / ATR, signed                   r12_1h    1h move over the last 12 bars / ATR, signed
  sess_*    session one hot                                      long      direction
Report: per feature AUC (positives vs negatives), a cross validated L2 logistic model
(5 fold AUC, accuracy at the 50% point), its coefficients, and the mechanical R of the
events the model would take versus skip, out of fold. Nothing here reads any year
outside the log window; a rule that comes out of it still has to pass the 2008 to 2016
gate in research_sd.py before a holdout is read.

Usage (repo folder):  python3 sd_discriminate.py DATA_DIR_1m [--symbol NQ]
Writes research/sd_discriminate.csv (one row per event with features, label, outcome) and research/sd_model.json (the fitted model, used by sd_model_gate.py).
"""
import os, sys, csv, glob, re
from datetime import datetime, timezone
import numpy as np

import research_sd as R
from research_sd import load_1m, resample, atr, ema
from sd_replay import replay, VARIANTS

OUT = "research"
FEATS = ["appr_max", "appr_net", "spike", "cons", "taps", "cin", "age", "zsize", "rej_pos", "rej_rng", "e21_5", "e21_15", "s21_15", "e50_4h", "hh_15",
         "vwap", "r12_1h", "sess_asia", "sess_london", "sess_nyam", "sess_nypm", "long"]


def session_vwap(T, H, L, C, V):
    sess = (T - 60 + 6 * 3600) // 86400; tp = (H + L + C) / 3; vw = np.full(len(T), np.nan)
    starts = np.concatenate([[0], np.flatnonzero(sess[1:] != sess[:-1]) + 1]); ends = np.concatenate([starts[1:], [len(T)]])
    for a, b in zip(starts, ends):
        cv = np.cumsum(V[a:b]); cp = np.cumsum(tp[a:b] * V[a:b])
        with np.errstate(invalid="ignore", divide="ignore"): vw[a:b] = cp / cv
    return vw


def swings(Hs, Ls, w=3):
    """Net count of higher highs and higher lows over the swing points in a window of 15m bars."""
    hi = [i for i in range(w, len(Hs) - w) if Hs[i] == Hs[i - w:i + w + 1].max()]; lo = [i for i in range(w, len(Ls) - w) if Ls[i] == Ls[i - w:i + w + 1].min()]
    s = 0
    for seq, arr in ((hi, Hs), (lo, Ls)):
        for a, b in zip(seq, seq[1:]): s += 1 if arr[b] > arr[a] else -1
    return s


def features(j, d, lo, hi, meta, B):
    T, O, H, L, C, A, e21, e50_4h_s, e21_15_s, s21_15_s, hh15_s, vw, r1h_s, mod = B
    a = A[j - 1] if A[j - 1] > 0 else 1e-9; rr = max(H[j] - L[j], 1e-9)
    hr = mod[j] // 60
    return dict(appr_max=(H[max(0, j - 5):j + 1] - L[max(0, j - 5):j + 1]).max() / a, appr_net=abs(C[j - 1] - C[max(0, j - 13)]) / a, spike=min(meta["spike"], 10),
                cons=min(meta["cons_atr"], 10), taps=min(meta["taps"], 20), cin=min(meta["cin"], 20), age=min(meta["age"], 1500) / 100, zsize=(hi - lo) / a,
                rej_pos=((C[j] - L[j]) / rr if d > 0 else (H[j] - C[j]) / rr), rej_rng=rr / a, e21_5=(C[j] - e21[j]) * d / a, e21_15=e21_15_s[j] * d / a,
                s21_15=s21_15_s[j] * d / a, e50_4h=e50_4h_s[j] * d / a, hh_15=hh15_s[j] * d, vwap=((C[j] - vw[j]) * d / a) if np.isfinite(vw[j]) else 0.0,
                r12_1h=r1h_s[j] * d / a, sess_asia=int(hr >= 18 or hr < 3), sess_london=int(3 <= hr < 7), sess_nyam=int(7 <= hr < 12), sess_nypm=int(12 <= hr < 17), long=int(d > 0))


def build_B(raw):
    """Bar series and the aligned higher timeframe features used by features(), from 1 minute arrays."""
    T, O, H, L, C, V = resample(*raw, 5); A = atr(H, L, C); e21 = ema(C, 21); mod = ((T // 60) % 1440).astype(int)
    T15, O15, H15, L15, C15, V15 = resample(*raw, 15); e21_15 = ema(C15, 21); s21_15 = np.r_[np.zeros(5), e21_15[5:] - e21_15[:-5]]
    hh = np.zeros(len(T15))
    for i in range(30, len(T15)): hh[i] = swings(H15[i - 30:i + 1], L15[i - 30:i + 1])
    T4, O4, H4, L4, C4, V4 = resample(*raw, 240); e50_4h = ema(C4, 50)
    T1, O1, H1, L1, C1, V1 = resample(*raw, 60); r1h = np.r_[np.zeros(12), C1[12:] - C1[:-12]]
    return (T, O, H, L, C, A, e21, align(T4, C4 - e50_4h, T, 1), align(T15, C15 - e21_15, T, 1), align(T15, s21_15, T, 1), align(T15, hh, T, 1),
            session_vwap(T, H, L, C, V), align(T1, r1h, T, 1), mod)


def align(Tb, X, T_trade, lag=0):
    idx = np.searchsorted(Tb, T_trade, side="right") - 1 - lag
    return np.where(idx >= 0, X[np.clip(idx, 0, len(X) - 1)], np.nan)


def auc(x, y):
    x = np.asarray(x, float); y = np.asarray(y, int); p, q = x[y == 1], x[y == 0]
    if len(p) == 0 or len(q) == 0: return float("nan")
    return (np.mean([(pi > q).mean() + 0.5 * (pi == q).mean() for pi in p]))


def logistic_fit(X, y, l2=1.0, iters=300):
    w = np.zeros(X.shape[1] + 1); Xb = np.column_stack([np.ones(len(X)), X])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ w)); g = Xb.T @ (p - y) + l2 * np.r_[0, w[1:]]
        Hs = Xb.T @ (Xb * (p * (1 - p))[:, None]) + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(Hs + 1e-6 * np.eye(len(w)), g)
    return w


def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    sym = args[args.index("--symbol") + 1] if "--symbol" in args else "NQ"
    cat = {re.sub(r"_full_1min.*$", "", os.path.basename(p)): p for p in glob.glob(os.path.join(args[0], "*_full_1min*"))}
    raw = load_1m(cat[sym])
    t0 = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()); keep = raw[0] >= t0; raw = tuple(x[keep] for x in raw)
    B = build_B(raw); T, O, H, L, C, A = B[0], B[1], B[2], B[3], B[4], B[5]; V = resample(*raw, 5)[5]; n = len(T); mod = B[13]; sess = (T - 60 + 6 * 3600) // 86400
    cfg = R.STATED; tick = R.TICKS.get(sym, 0.25)
    w0 = int(datetime.strptime(R.LOG_WINDOW[0], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()); w1 = int(datetime.strptime(R.LOG_WINDOW[1], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    sig = [s for s in R.scan_signals((T, O, H, L, C, V), cfg["spike"], cfg["cons"], cfg["approach"], tick) if w0 <= T[s["j"]] < w1]
    # Adam's setups: rank 1 reconstructed zones
    his = []
    for c in csv.DictReader(open(os.path.join(OUT, "sd_zone_candidates.csv"))):
        if c["rank"] != "1": continue
        te = int(datetime.strptime(c["rejection_bar_end"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()); j = int(np.searchsorted(T, te))
        if j < n and T[j] == te: his.append(dict(j=j, dir=1 if c["dir"] == "Long" else -1, lo=float(c["zone_low"]), hi=float(c["zone_high"]), taken=c["result"] != "Scratch",
                                                 spike=float(c["spike_mult"]), cons_atr=float(c["cons_atr"]), taps=int(c["taps"]), cin=int(c["closes_inside"]), age=int(c["age_bars"]), id=c["notion_id"]))
    events = []; matched = set()
    for s in sig:
        lab = 0; mid = ""
        for h in his:
            if h["dir"] == s["dir"] and abs(h["j"] - s["j"]) <= 2 and min(h["hi"], s["hi"]) >= max(h["lo"], s["lo"]) - 0.5: lab = 1; mid = h["id"]; matched.add(h["id"]); break
        events.append(dict(src="engine", label=lab, id=mid, j=s["j"], dir=s["dir"], lo=s["lo"], hi=s["hi"], meta=s))
    for h in his:
        if h["id"] not in matched: events.append(dict(src="adam_only", label=1, id=h["id"], j=h["j"], dir=h["dir"], lo=h["lo"], hi=h["hi"], meta=h))
    rows = []
    for e in events:
        f = features(e["j"], e["dir"], e["lo"], e["hi"], e["meta"], B)
        out = replay(e["j"], e["dir"], e["hi"], e["lo"], T, O, H, L, C, A, mod, sess, None)
        if out is None: continue
        rows.append(dict(src=e["src"], label=e["label"], notion_id=e["id"], time=datetime.fromtimestamp(int(T[e["j"]]), timezone.utc).strftime("%Y-%m-%d %H:%M"), dir=e["dir"],
                         fixed_3R=round(out["fixed_3R"], 3), be_2R=round(out["be_2R"], 3), **{k: round(float(v), 4) for k, v in f.items()}))
    with open(os.path.join(OUT, "sd_discriminate.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    y = np.array([r["label"] for r in rows]); X = np.array([[r[k] for k in FEATS] for r in rows], float); R3 = np.array([r["fixed_3R"] for r in rows])
    eng = np.array([r["src"] == "engine" for r in rows])
    print(f"engine fires in the window: {eng.sum()}, of which matching Adam's setups: {(y[eng] == 1).sum()}; Adam's setups the engine never fired on: {(~eng).sum()}")
    print(f"mechanical fixed_3R: Adam's picks {R3[y == 1].mean():+.3f} (n={(y == 1).sum()}), engine fires he skipped {R3[y == 0].mean():+.3f} (n={(y == 0).sum()})\n")
    print(f"{'feature':12s} {'AUC':>6s} {'Adam mean':>10s} {'skip mean':>10s}")
    order = sorted(range(len(FEATS)), key=lambda k: -abs(auc(X[:, k], y) - 0.5))
    for k in order: print(f"{FEATS[k]:12s} {auc(X[:, k], y):6.2f} {X[y == 1, k].mean():10.2f} {X[y == 0, k].mean():10.2f}")
    # cross validated logistic model
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = (X - mu) / sd; rng = np.random.default_rng(7); folds = rng.integers(0, 5, len(y)); p_oof = np.zeros(len(y))
    for f in range(5):
        tr, te = folds != f, folds == f
        if te.sum() == 0 or len(set(y[tr])) < 2: continue
        w = logistic_fit(Z[tr], y[tr], l2=3.0); p_oof[te] = 1 / (1 + np.exp(-(np.column_stack([np.ones(te.sum()), Z[te]]) @ w)))
    w = logistic_fit(Z, y, l2=3.0)
    import json; json.dump(dict(feats=FEATS, mu=mu.tolist(), sd=sd.tolist(), w=w.tolist(), window=list(R.LOG_WINDOW)), open(os.path.join(OUT, "sd_model.json"), "w"))
    print(f"\nlogistic model, 5 fold out of fold: AUC {auc(p_oof, y):.2f}, accuracy {((p_oof > 0.5) == (y == 1)).mean() * 100:.0f}% (base rate {y.mean() * 100:.0f}% positives)")
    print("coefficients (standardised): " + ", ".join(f"{FEATS[k]} {w[k + 1]:+.2f}" for k in np.argsort(-np.abs(w[1:]))[:10]))
    take = p_oof >= np.median(p_oof)
    print(f"\nout of fold selection: model takes {take.sum()} events, mechanical fixed_3R {R3[take].mean():+.3f}; skips {(~take).sum()}, {R3[~take].mean():+.3f}; all {R3.mean():+.3f}")
    take2 = p_oof >= np.quantile(p_oof, 0.75)
    print(f"top quarter by model score: {take2.sum()} events, fixed_3R {R3[take2].mean():+.3f}")
    print(f"\n-> {OUT}/sd_discriminate.csv")


if __name__ == "__main__":
    main()
