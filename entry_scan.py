"""Entry scanner for resting order execution.

Reproduces the frozen engine's line detection (backtest_hull.run at MINSPAN 2160,
MAXSPAN 17520, intrabar, causal) without the position manager, and adds the
one thing the live bot needs that the engine cannot give: at the close of bar
t, where will each line that could legitimately break on bar t+1 sit, and
what stop would the engine assign if it does.

Three public functions:

  scan(path)                 -> ScanState: arrays, pivots, hull state at the last
                                bar, and every candidate signal per bar with its
                                line key (a, b, kind), exactly as the engine
                                iterates them.
  taken_edges(state, trades) -> the set of line keys the engine has traded,
                                recovered by replaying the engine's own trade
                                list against the candidates (exact: the research
                                harness reproduces 17440/17440 trades this way).
  next_bar_orders(state, taken) -> for the bar after the last one: at most one
                                order per direction, at the level that would be
                                touched first, with the engine's prequalified
                                stop. Only lines whose refit geometry and stop
                                already pass on data through the last bar.

The engine's acceptance on the break bar also uses that bar's ATR and 200 EMA
and pivots confirmed by it, so a filled order is CONFIRMED or SCRATCHED when
the engine runs at the next close. On 18 years the prequalified set confirms
99% of the time (research/intrabar/report.md).
"""
from collections import defaultdict
import numpy as np
from backtest_hull import load_series, ema, atr, pivots

MINSPAN, MAXSPAN = 2160, 17520
TOL, TOUCH_BAND, BRK_TOL = 0.0015, 0.0005, 0.0002
SPANDAYS, K, MINTOUCH, TGAP = 7, 3, 3, 6


class ScanState:
    pass


def _refit(T, H, L, piv, arr, sign, a, m, t, hv, check_break=True):
    """The engine's refit, with the break check optional so it can be evaluated
    for bar t using only data through t-1."""
    cand = []
    for p in piv:
        if p < a or p > t: continue
        if p > t - K: continue
        ln = arr[a] + m * (p - a); g = (arr[p] - ln) if sign > 0 else (ln - arr[p])
        if -BRK_TOL * arr[p] <= g <= 0.005 * arr[p]: cand.append(int(p))
    if len(cand) < MINTOUCH: return None
    best = None
    for x in range(len(cand)):
        p1 = cand[x]
        if p1 not in hv: continue
        if (T[t] if t < len(T) else T[-1] + 3600 * (t - len(T) + 1)) - T[p1] < SPANDAYS * 86400: continue
        for y in range(x + 1, len(cand)):
            p2 = cand[y]
            if p2 - p1 < TGAP: continue
            s = (arr[p2] - arr[p1]) / (p2 - p1)
            if (sign > 0 and s <= 0) or (sign < 0 and s >= 0): continue
            zz = np.arange(p1, t); lnz = arr[p1] + s * (zz - p1)
            if (sign > 0 and np.any(L[p1:t] < lnz - BRK_TOL * L[p1:t])) or \
               (sign < 0 and np.any(H[p1:t] > lnz + BRK_TOL * H[p1:t])): continue
            lnt = arr[p1] + s * (t - p1); lnp = arr[p1] + s * (t - 1 - p1)
            if check_break:
                if sign > 0:
                    if not (L[t] <= lnt and L[t - 1] > lnp): continue
                else:
                    if not (H[t] >= lnt and H[t - 1] < lnp): continue
            g = (arr[p1:t] - lnz) if sign > 0 else (lnz - arr[p1:t])
            mask = (g >= -BRK_TOL * arr[p1:t]) & (g <= TOUCH_BAND * arr[p1:t])
            tt = _sepidx([int(z) for z in zz[mask]])
            if len(tt) >= MINTOUCH:
                score = (len(tt), p2 - p1)
                if best is None or score > best[0]: best = (score, int(p1), float(s), int(p2), tt)
    if best is None: return None
    _, p1, s, p2, tt = best
    return p1, s, p2, tt


def _sepidx(idxs):
    out = []
    for z in sorted(idxs):
        if not out or z - out[-1] >= TGAP: out.append(int(z))
    return out


def _stop_for(H, L, e200, A, sh, rh, d, entry, t):
    """The engine's stop candidate for an entry at bar t (uses A[t], e200[t])."""
    floor = 1.0 * A[t]
    if d < 0:
        cands = []
        for j in range(1, len(rh)):
            aa, bb = rh[j - 1], rh[j]; mm = (H[bb] - H[aa]) / (bb - aa); val = H[aa] + mm * (t - aa)
            if val > entry + floor and bb >= t - 720 and aa >= t - 2880: cands.append(float(val))
        cands.sort()
        if cands: return cands[0], 'auto'
        if e200[t] > entry + floor: return float(e200[t]), 'ema'
    else:
        cands = []
        for j in range(1, len(sh)):
            aa, bb = sh[j - 1], sh[j]; mm = (L[bb] - L[aa]) / (bb - aa); val = L[aa] + mm * (t - aa)
            if val < entry - floor and bb >= t - 720 and aa >= t - 2880: cands.append(float(val))
        cands.sort(reverse=True)
        if cands: return cands[0], 'auto'
        if e200[t] < entry - floor: return float(e200[t]), 'ema'
    return None, None


def scan(path, start_ts=None, upto=None):
    T, O, H, L, C = load_series(path)
    if upto is not None:
        T, O, H, L, C = T[:upto], O[:upto], H[:upto], L[:upto], C[:upto]
    n = len(C)
    e21 = ema(C, 21); e200 = ema(C, 200); A = atr(H, L, C, 14)
    PH, PL = pivots(H, L, K)
    start = int(np.searchsorted(T, start_ts)) if start_ts else 0
    sh = []; rh = []; ih = 0; il = 0
    sigs = []

    def sl_low(i, j): return (L[j] - L[i]) / (j - i)
    def sl_high(i, j): return (H[j] - H[i]) / (j - i)

    for t in range(210, n):
        while il < len(PL) and PL[il] + K <= t:
            p = PL[il]
            while len(sh) >= 2 and sl_low(sh[-2], sh[-1]) >= sl_low(sh[-1], p): sh.pop()
            sh.append(p); il += 1
        while ih < len(PH) and PH[ih] + K <= t:
            p = PH[ih]
            while len(rh) >= 2 and sl_high(rh[-2], rh[-1]) <= sl_high(rh[-1], p): rh.pop()
            rh.append(p); ih += 1
        if t < start: continue
        order = 0
        for i in range(1, len(sh)):
            a, b = sh[i - 1], sh[i]; m = sl_low(a, b)
            if m <= 0 or (t - a) < MINSPAN or (t - a) > MAXSPAN: continue
            lt = L[a] + m * (t - a); lp = L[a] + m * (t - 1 - a)
            if not (L[t] <= lt and L[t - 1] > lp): continue
            zz = np.arange(a, t)
            if np.any(L[a:t] < L[a] + m * (zz - a) - TOL * L[a:t]): continue
            rf = _refit(T, H, L, PL, L, 1, a, m, t, set(sh))
            if rf is None: continue
            a2, m2, _, tch = rf
            lt2 = L[a2] + m2 * (t - a2)
            entry = O[t] if O[t] < lt2 else lt2
            stop, src = _stop_for(H, L, e200, A, sh, rh, -1, entry, t)
            if stop is None or stop - entry <= 0: continue
            sigs.append(dict(dir=-1, t0=int(t), entry=float(entry), stop0=float(stop), a=int(a2),
                             kind='sup', touches=len(tch), stop_src=src, edge=(int(a), int(b), 's'), order=order))
            order += 1
        for i in range(1, len(rh)):
            a, b = rh[i - 1], rh[i]; m = sl_high(a, b)
            if m >= 0 or (t - a) < MINSPAN or (t - a) > MAXSPAN: continue
            lt = H[a] + m * (t - a); lp = H[a] + m * (t - 1 - a)
            if not (H[t] >= lt and H[t - 1] < lp): continue
            zz = np.arange(a, t)
            if np.any(H[a:t] > H[a] + m * (zz - a) + TOL * H[a:t]): continue
            rf = _refit(T, H, L, PH, H, -1, a, m, t, set(rh))
            if rf is None: continue
            a2, m2, _, tch = rf
            lt2 = H[a2] + m2 * (t - a2)
            entry = O[t] if O[t] > lt2 else lt2
            stop, src = _stop_for(H, L, e200, A, sh, rh, 1, entry, t)
            if stop is None or entry - stop <= 0: continue
            sigs.append(dict(dir=1, t0=int(t), entry=float(entry), stop0=float(stop), a=int(a2),
                             kind='res', touches=len(tch), stop_src=src, edge=(int(a), int(b), 'r'), order=order))
            order += 1

    st = ScanState()
    st.T, st.O, st.H, st.L, st.C, st.e21, st.e200, st.A = T, O, H, L, C, e21, e200, A
    st.PH, st.PL, st.sh, st.rh, st.sigs, st.n = PH, PL, sh, rh, sigs, n
    return st


def taken_edges(state, engine_trades):
    """Replay the engine's selection rule over the candidates to recover the
    set of lines it has traded. Returns (taken set, matched count)."""
    by_bar = defaultdict(list)
    for sg in state.sigs: by_bar[sg["t0"]].append(sg)
    taken, matched = set(), 0
    for tr in engine_trades:
        for sg in sorted(by_bar.get(tr["t0"], []), key=lambda x: x["order"]):
            if sg["edge"] in taken or sg["dir"] != tr["dir"]: continue
            if abs(sg["entry"] - tr["entry"]) > 1e-6 * max(1.0, abs(tr["entry"])): continue
            taken.add(sg["edge"]); matched += 1
            break
    return taken, matched


def next_bar_orders(state, taken):
    """Orders to rest for bar n (the one after the last cached bar n-1).

    For each direction, every line that (a) is in the span band, (b) has not
    been traded, (c) price sits on the right side of at the last bar, (d) has
    never been pierced, (e) passes the refit geometry on data through n-1, and
    (f) has a valid engine stop for an entry at its level. Returns at most one
    order per direction: the level that would be touched first, i.e. the
    highest qualifying line for a short, the lowest for a long.
    Each order: dict(dir, trigger, stop, stop_src, edge, line_level, refit_level)."""
    T, O, H, L, C, e200, A = state.T, state.O, state.H, state.L, state.C, state.e200, state.A
    n = state.n; t = n              # projecting to bar n; last known bar is n-1
    last = n - 1
    sh, rh = state.sh, state.rh
    out = {}

    for d, hull, piv, arr in ((-1, sh, state.PL, L), (1, rh, state.PH, H)):
        best = None
        for i in range(1, len(hull)):
            a, b = hull[i - 1], hull[i]
            key = (int(a), int(b), 's' if d < 0 else 'r')
            if key in taken: continue
            m = (arr[b] - arr[a]) / (b - a)
            if (d < 0 and m <= 0) or (d > 0 and m >= 0): continue
            if (t - a) < MINSPAN or (t - a) > MAXSPAN: continue
            lt = arr[a] + m * (t - a); lp = arr[a] + m * (last - a)
            # price must be on the far side of the line at the last bar
            if d < 0 and not (L[last] > lp): continue
            if d > 0 and not (H[last] < lp): continue
            zz = np.arange(a, t)
            if d < 0 and np.any(L[a:t] < arr[a] + m * (zz - a) - TOL * L[a:t]): continue
            if d > 0 and np.any(H[a:t] > arr[a] + m * (zz - a) + TOL * H[a:t]): continue
            rf = _refit(T, H, L, piv, arr, 1 if d < 0 else -1, a, m, t, set(hull), check_break=False)
            if rf is None: continue
            a2, m2, _, tch = rf
            lt2 = arr[a2] + m2 * (t - a2); lp2 = arr[a2] + m2 * (last - a2)
            if d < 0 and not (L[last] > lp2): continue
            if d > 0 and not (H[last] < lp2): continue
            # both the raw line and the refit line must be breached: rest at the deeper one
            trigger = min(lt, lt2) if d < 0 else max(lt, lt2)
            stop, src = _stop_for(H, L, e200, A, sh, rh, d, lt2, last)
            if stop is None: continue
            if (d < 0 and stop - lt2 <= 0) or (d > 0 and lt2 - stop <= 0): continue
            cand = dict(dir=d, trigger=float(trigger), stop=float(stop), stop_src=src, edge=key,
                        line_level=float(lt), refit_level=float(lt2), touches=len(tch), span=int(t - a))
            if best is None or (d < 0 and trigger > best["trigger"]) or (d > 0 and trigger < best["trigger"]):
                best = cand
        if best is not None:
            out[d] = best
    return out
