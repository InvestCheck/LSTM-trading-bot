"""Protocol v2 gate: tier score and cost cap for a candidate resting order.

Scores a candidate exactly as research_model.py scored the 2008 to 2016 fit,
from the frozen file research/tier_model.json, using only what is known at the
close of the bar BEFORE the order fills (the bar the order is placed on).

v2 executes a signal only if
  1. the instrument's average round trip cost is <= COST_CAP (v2_config.json), and
  2. the candidate's tier score is >= the frozen cutoff (the exploration median).

Feature order must match research_model.NAMES exactly; it is asserted against
the names stored in the frozen file.
"""
import json, math, os
import numpy as np
from datetime import datetime, timezone
from backtest_hull import ema

CLASSES = {
    "FX": "A6 AD B6 CNH E1 E6 E7 J1 J7 MP N6 NOK SEK RP RY SIR DX".split(),
    "EQ": "ES NQ RTY EW NIY NKD YM FDAX FDXM FESX FXXP FCE FTI FTUK MFS MME".split(),
    "RATES": "ZT ZF ZN TN UB FGBL FGBM FGBX FOAT FBTP FBON G".split(),
    "ENERGY": "CL BZ B HO RB NG".split(),
    "METALS": "GC MGC SI HG PA PL".split(),
    "AGS": "ZC XC ZS ZL ZM KE CT SB RS DC GF HE LE".split(),
}
PRE_ORDER = ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20", "p_ext_1y", "p_atr_ratio", "p_risk_atr"]
NAMES = PRE_ORDER + ["log_span", "touches", "is_long", "stop_ema", "hour_sin", "hour_cos", "sunday", "inst_cost"] + list(CLASSES)


class Tier:
    def __init__(self, model_path="research/tier_model.json", config_path="v2_config.json"):
        m = json.load(open(model_path))
        assert m["names"] == NAMES, "feature order in tier.py no longer matches the frozen model"
        self.mu = np.array(m["mu"]); self.sd = np.array(m["sd"])
        self.lo = np.array(m["clip_lo"]); self.hi = np.array(m["clip_hi"]); self.zclip = m.get("z_clip", 5.0)
        self.w = np.array(m["weights"]); self.b = m["intercept"]; self.cutoff = m["cutoff"]
        cfg = json.load(open(config_path))
        self.cost_cap = cfg["cost_cap"]; self.inst_cost = cfg["inst_cost"]; self.cheap = set(cfg["cheap"])
        self.fit_years = m.get("fit_years", "?")

    def features(self, sym, st, order, next_bar_ts):
        """Feature vector for a candidate from entry_scan.next_bar_orders, using
        the scan state's last bar (the bar the order is placed on)."""
        p = st.n - 1
        C, H, L, A, e21, e200 = st.C, st.H, st.L, st.A, st.e21, st.e200
        e50 = ema(C, 50)
        ap = A[p] if A[p] > 0 else 1e-12
        d, entry, stop = order["dir"], order["refit_level"], order["stop"]
        bandp = e21[p] + 3.5 * ap if d > 0 else e21[p] - 3.5 * ap
        hi1 = float(np.max(H[max(0, p - 5799):p + 1])); lo1 = float(np.min(L[max(0, p - 5799):p + 1]))
        dt = datetime.fromtimestamp(int(next_bar_ts), timezone.utc)
        cls = next((c for c, lst in CLASSES.items() if sym in lst), "OTHER")
        x = [
            d * (C[p] - e21[p]) / ap, d * (C[p] - e50[p]) / ap, d * (C[p] - e200[p]) / ap,
            d * (bandp - entry) / ap,
            d * (C[p] - C[max(0, p - 5)]) / ap, d * (C[p] - C[max(0, p - 20)]) / ap,
            ((entry - hi1) if d > 0 else (lo1 - entry)) / ap,
            ap / max(1e-12, float(np.mean(A[max(0, p - 500):p]))) if p > 50 else 1.0,
            abs(entry - stop) / ap,
            math.log(max(1, order["span"])), order["touches"], 1.0 if d > 0 else 0.0,
            1.0 if order["stop_src"] == "ema" else 0.0,
            math.sin(2 * math.pi * dt.hour / 24), math.cos(2 * math.pi * dt.hour / 24),
            1.0 if dt.weekday() == 6 else 0.0, self.inst_cost.get(sym, 0.1),
        ] + [1.0 if cls == c else 0.0 for c in CLASSES]
        return np.array(x, float)

    def score(self, sym, st, order, next_bar_ts):
        x = self.features(sym, st, order, next_bar_ts)
        x[~np.isfinite(x)] = 0.0
        x = np.clip(x, self.lo, self.hi)
        z = np.clip((x - self.mu) / self.sd, -self.zclip, self.zclip)
        return float(self.b + z @ self.w)

    def allows(self, sym, st, order, next_bar_ts):
        """(execute?, score, reason)"""
        if sym not in self.cheap:
            return False, None, f"cost {self.inst_cost.get(sym, float('nan')):.3f}R > cap"
        sc = self.score(sym, st, order, next_bar_ts)
        if sc < self.cutoff:
            return False, sc, f"score {sc:+.4f} < cutoff {self.cutoff:+.4f}"
        return True, sc, f"score {sc:+.4f}"
