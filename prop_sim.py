#!/usr/bin/env python3
"""Prop firm simulation for the trendline bot (v2 gate, optional stop rule).

Universe: the v2 instruments that have a CME micro or mini (MICROS below).
Each v2 trade becomes session only P&L per contract: flat at the 16:00 ET bar
close (the firm liquidates before the 17:00 ET close), re entry at the 18:00 ET
open if the engine still holds, no weekend holds, commissions and one tick of
slippage each way on every entry and re entry. Entry fill = the deeper line
plus one tick (what the live bot pays).

Then every trading day from 2017 to 2026 starts an evaluation under a plan's
rules; a pass continues into the funded phase until the account busts. Sizing
is contracts = round(risk_dollars / (stop distance x contract multiplier)),
risk_dollars a fraction of the plan's drawdown, with separate eval and funded
fractions and a size down once funded profit exceeds a buffer.

Rules implemented per plan: profit target, trailing drawdown (end of day or
intraday) that locks at the starting balance once earned, consistency rule
(best day as a share of profit) for passing and for payouts, payout
eligibility by winning days, payout as a fraction of profit with a split, and
after a payout the floor moves to the starting balance (balance cannot go below
zero profit). Fees: eval per month, activation. Edit PLANS to match the firm.

Usage (repo folder):  python3 prop_sim.py DATA_DIR [--stop-rule] [--plan NAME] [--hold] [--no-consistency]
                      python3 prop_sim.py --trades research/vwap_trades_primary.csv [--plan NAME]
  --trades CSV      run the plans on an intraday trade file (columns session, R_unit, pnl_usd) instead of the
                    trendline bot; each trade is one day's P&L per contract
  --hold            hold through the close and weekends (a swing plan), no forced flat or re entries
  --no-consistency  ignore the consistency rule for passing and payouts (ceiling test)
Writes research/prop_report.md.
"""
import os, sys, math, json, csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import numpy as np

from instruments import TICKS
try:                                   # the trendline bot path needs the research modules; --trades does not
    from research_exits import harvest, features, exit_engine, rolling_extreme
    from research_model import TICK_FIX
    from research_v3 import TierScorer
    from batch_backtest import build_catalog, iso
    from backtest_hull import load_series
except ImportError:
    harvest = None

OUT = "research"
WARMUP_DAYS = 60
START_YEAR = 2017
STOP_MAX_ATR = 2.5

# vendor symbol -> (micro/mini name, dollars per 1.0 of vendor price, commission per side per contract)
MICROS = {
    "ES": ("MES", 5, 1.5), "NQ": ("MNQ", 2, 1.5), "RTY": ("M2K", 5, 1.5), "YM": ("MYM", 0.5, 1.5),
    "GC": ("MGC", 10, 1.5), "SI": ("SIL", 1000, 1.5), "HG": ("MHG", 2500, 1.5), "CL": ("MCL", 100, 1.5),
    "NG": ("QG", 2500, 1.5), "E6": ("M6E", 12500, 1.5), "A6": ("M6A", 10000, 1.5), "B6": ("M6B", 6250, 1.5),
    "J1": ("MJY", 1250000, 1.5), "E1": ("MSF", 12500, 1.5), "XC": ("XC", 10, 2.0),
}
def topstep(size, target, dd, fee_month, activation, dll, name):
    return dict(start=size, target=target, dd=dd, dd_mode="eod", consistency_eval=0.55, consistency_payout=0.55,
                payout_win_days=5, payout_win_min=200, payout_frac=0.50, split=0.90, eval_fee_month=fee_month,
                activation=activation, max_contracts=size // 1000, daily_loss=dll, label=name)

PLANS = {}
for size, target, dd, std, nafee, rta in ((50000, 3000, 2000, 49, 95, 85), (100000, 6000, 3000, 99, 149, 129),
                                         (150000, 9000, 4500, 199, 229, 199)):
    k = size // 1000; dll = dd // 2 if size == 50000 else (2000 if size == 100000 else 3000)
    PLANS[f"topstep{k}_std"] = topstep(size, target, dd, std, 149, dll, f"Topstep {k}K standard: ${std}/mo, $149 activation, daily loss ${dll}")
    PLANS[f"topstep{k}_noact"] = topstep(size, target, dd, nafee, 0, None, f"Topstep {k}K no activation: ${nafee}/mo, no daily loss limit")
    PLANS[f"topstep{k}_rta"] = topstep(size, target, dd, rta, 0, dll, f"Topstep {k}K no activation + RTA: ${rta}/mo, daily loss ${dll}")
PLANS["tradeify150"] = dict(start=150000, target=9000, dd=4500, dd_mode="eod", consistency_eval=0.40, consistency_payout=0.40,
                            payout_win_days=5, payout_win_min=200, payout_frac=0.50, split=0.90,
                            eval_fee_month=0, eval_fee_once=340, activation=0, max_contracts=150, daily_loss=None,
                            label="Tradeify 150K: $340 once")
PLANS["tradeify50"] = dict(start=50000, target=3000, dd=2000, dd_mode="eod", consistency_eval=0.40, consistency_payout=0.40,
                           payout_win_days=5, payout_win_min=200, payout_frac=0.50, split=0.90,
                           eval_fee_month=0, eval_fee_once=99.95, activation=0, max_contracts=50, daily_loss=None,
                           label="Tradeify 50K: $99.95 once")
EVAL_RISK = [0.05, 0.10, 0.20, 0.33, 0.50]            # fraction of the drawdown risked per trade in the eval
FUNDED = [(0.33, 0.10), (0.20, 0.10), (0.20, 0.20), (0.10, 0.10)]   # (risk until profit >= one drawdown, risk after)
# note: one micro contract needs risk >= half its dollar R (about $100 to $400), so fractions below ~5% of a
# 4,500 drawdown stop the account trading altogether
MAX_EVAL_DAYS = 365
FLAT_AT_CLOSE = True


def session_day(ts):
    """Trading day key: bars from 18:00 ET belong to the next calendar day's session."""
    dt = datetime.fromtimestamp(int(ts), timezone.utc)          # vendor timestamps are ET labelled as UTC
    if dt.hour >= 18: dt = dt + timedelta(days=1)
    return dt.date()


def build_trades(cat, syms, stop_rule):
    """v2 trades on the micro universe, as per contract session P&L by day and by bar."""
    tier = TierScorer(); out = []
    for sym in syms:
        if sym not in cat or sym not in MICROS or sym not in tier.cheap: continue
        micro, mult, comm = MICROS[sym]
        tick = TICK_FIX.get(sym, TICKS.get(sym, 0.0))
        T = load_series(cat[sym])[0]; start_ts = int(T.min()) + WARMUP_DAYS * 86400
        D, sigs = harvest(cat[sym], start_ts=start_ts)
        D["hi1"] = rolling_extreme(D["H"], 5800, True); D["lo1"] = rolling_extreme(D["L"], 5800, False)
        D["hi5"] = rolling_extreme(D["H"], 29000, True); D["lo5"] = rolling_extreme(D["L"], 29000, False)
        O, H, L, C, A, TT = D["O"], D["H"], D["L"], D["C"], D["A"], D["T"]
        by_bar = defaultdict(list)
        for sg in sigs: by_bar[sg["t0"]].append(sg)
        busy, taken = -1, set()
        for t in sorted(by_bar):
            if t < busy: continue
            for sg in sorted(by_bar[t], key=lambda x: x["order"]):
                if sg["edge"] in taken: continue
                taken.add(sg["edge"])
                ei, ex, why, mfe = exit_engine(D, sg); busy = ei
                f = features(D, sg)
                row = dict(symbol=sym, dir=sg["dir"], touches=sg["touches"], span=sg["t0"] - sg["a"], hour=f["hour"], dow=f["dow"],
                           stop_src=sg["stop_src"], inst_cost=tier.inst_cost[sym],
                           **{k: f[k] for k in ["p_d_e21", "p_d_e50", "p_d_e200", "p_room", "p_mom5", "p_mom20", "p_ext_1y", "p_atr_ratio", "p_risk_atr"]})
                if tier.score(row) < tier.cutoff: break
                if stop_rule and f["risk_atr"] > STOP_MAX_ATR: break
                if int(iso(TT[sg["t0"]])[:4]) < START_YEAR - 1: break
                d, t0 = sg["dir"], sg["t0"]
                arr = L if d < 0 else H; a, b, _ = sg["edge"]; m = (arr[b] - arr[a]) / (b - a)
                lt_raw = arr[a] + m * (t0 - a); lt2 = arr[sg["a"]] + sg["m2"] * (t0 - sg["a"])
                trig = (min(lt_raw, lt2) if d < 0 else max(lt_raw, lt2))
                fill = (O[t0] if (d < 0 and O[t0] < trig) or (d > 0 and O[t0] > trig) else trig) - d * tick
                R_px = abs(fill - sg["stop0"])
                if R_px <= 0: break
                # session only P&L per contract, bar by bar; flat from the 16:00 bar close to the 18:00 open
                pnl_day, path_day = defaultdict(float), defaultdict(list)
                held, last_px = True, fill
                for u in range(t0, ei + 1):
                    hr = datetime.fromtimestamp(int(TT[u]), timezone.utc).hour
                    day = session_day(TT[u])
                    if not held:
                        if hr == 18 and u < ei:          # re entry at the open; pay a tick and commissions
                            held, last_px = True, O[u] + d * tick
                            pnl_day[day] -= 2 * comm
                        elif u == ei:                    # engine exited while we were flat: nothing to realise
                            break
                        else:
                            continue
                    px_end = ex if u == ei else C[u]
                    pnl_day[day] += (px_end - last_px) * d * mult
                    path_day[day].append(((px_end - last_px) * d * mult, ((L[u] if d > 0 else H[u]) - last_px) * d * mult))
                    last_px = px_end
                    if u == ei:
                        pnl_day[day] -= 2 * comm + tick * mult; break
                    if FLAT_AT_CLOSE and hr == 16:        # forced flat before the close
                        pnl_day[day] -= 2 * comm + tick * mult; held = False
                    elif FLAT_AT_CLOSE and hr == 17:
                        held = False
                if t0 == ei: pnl_day[session_day(TT[t0])] -= 2 * comm + tick * mult
                out.append(dict(symbol=sym, micro=micro, entry_day=session_day(TT[t0]), R_unit=R_px * mult,
                                pnl_day=dict(pnl_day), path_day={k: v for k, v in path_day.items()}))
                break
        print(f"{sym:5s} -> {micro:4s} {sum(1 for x in out if x['symbol'] == sym)} trades")
    out.sort(key=lambda x: x["entry_day"])
    return out


def simulate_plan(plan, trades, days, eval_risk, f_risk, f_risk_after, seed=0):
    """One eval attempt starting on each day in `days`. Returns per attempt records."""
    P = plan; dd = P["dd"]
    by_day = defaultdict(list)
    for tr in trades: by_day[tr["entry_day"]].append(tr)
    recs = []
    for d0 in days:
        bal, hwm, floor_ = 0.0, 0.0, -dd                      # profit relative to the start balance
        phase, day_i, cur = "eval", 0, d0
        open_trades = []; daily = []; fees = 0.0; payouts = 0.0; win_days = 0; locked = False
        months = 0; t_pass = None; busted = False; funded_days = 0
        while True:
            # fees: a one time eval fee, or a monthly subscription while in the eval
            if phase == "eval":
                if day_i == 0: fees += P.get("eval_fee_once") or P.get("eval_fee_month", 0)
                elif day_i % 30 == 0 and not P.get("eval_fee_once"): fees += P.get("eval_fee_month", 0)
            # new trades today
            risk_frac = eval_risk if phase == "eval" else (f_risk if bal < dd else f_risk_after)
            for tr in by_day.get(cur, []):
                n = int(round(risk_frac * dd / tr["R_unit"]))      # nearest whole contract; 1 contract needs risk >= half its R
                n = min(n, P["max_contracts"])
                if n >= 1: open_trades.append((tr, n))
            # today's P&L and intraday path
            day_pnl = 0.0; worst_intraday = 0.0; run = 0.0
            for tr, n in open_trades:                                   # in order; a daily loss limit locks the day out
                if cur in tr["pnl_day"]: day_pnl += n * tr["pnl_day"][cur]
                if P.get("daily_loss") and day_pnl <= -P["daily_loss"]: break      # later trades that day are not taken
            if P["dd_mode"] == "intraday":
                # approximate: sum of per trade intraday lows (conservative)
                worst_intraday = sum(n * min((lo for _, lo in tr["path_day"].get(cur, [(0, 0)])), default=0) for tr, n in open_trades)
            open_trades = [(tr, n) for tr, n in open_trades if max(tr["pnl_day"]) > cur]
            # drawdown check
            if P["dd_mode"] == "intraday" and bal + worst_intraday < floor_:
                busted = True
            bal += day_pnl; daily.append(day_pnl)
            if day_pnl >= P["payout_win_min"]: win_days += 1
            if bal < floor_: busted = True
            if busted: break
            if bal > hwm:
                hwm = bal
                if not locked: floor_ = max(floor_, hwm - dd)
                if hwm >= dd and not locked: floor_, locked = max(floor_, 0.0), True
            # phase transitions
            if phase == "eval":
                best = max(daily) if daily else 0
                if bal >= P["target"] and (best <= P["consistency_eval"] * bal):
                    phase, t_pass = "funded", day_i; fees += P["activation"]; daily = []; win_days = 0
                    bal, hwm, floor_, locked = 0.0, 0.0, -dd, False       # funded account starts fresh
                elif day_i >= MAX_EVAL_DAYS:
                    break
            else:
                funded_days += 1
                best = max(daily) if daily else 0
                if win_days >= P["payout_win_days"] and bal > 0 and best <= P["consistency_payout"] * max(bal, 1e-9):
                    amt = P["payout_frac"] * bal
                    payouts += P["split"] * amt; bal -= amt; hwm = bal; floor_, locked = 0.0, True
                    daily = []; win_days = 0
                if funded_days > 3 * 365: break
            day_i += 1; cur = cur + timedelta(days=1)
            if cur > days[-1]: break
        recs.append(dict(start=d0, passed=t_pass is not None, days_to_pass=t_pass, fees=fees, payouts=payouts,
                         busted=busted, funded_days=funded_days))
    return recs


def main():
    args = sys.argv[1:]
    if not args: sys.exit("usage: python3 prop_sim.py DATA_DIR [--stop-rule] [--plan NAME]")
    stop_rule = "--stop-rule" in args
    trades_csv = args[args.index("--trades") + 1] if "--trades" in args else None
    global FLAT_AT_CLOSE
    if "--hold" in args: FLAT_AT_CLOSE = False
    if "--no-consistency" in args:
        for P in PLANS.values(): P["consistency_eval"] = P["consistency_payout"] = 1.0
    plans = [args[args.index("--plan") + 1]] if "--plan" in args else list(PLANS)
    if trades_csv:
        trades = []
        for r in csv.DictReader(open(trades_csv)):
            d = datetime.strptime(r["session"], "%Y-%m-%d").date(); pnl = float(r["pnl_usd"])
            trades.append(dict(symbol=r["symbol"], micro=r.get("micro", ""), entry_day=d, R_unit=float(r["R_unit"]),
                               pnl_day={d: pnl}, path_day={d: [(pnl, min(0.0, pnl))]}))
        trades.sort(key=lambda x: x["entry_day"])
        print(f"{len(trades)} trades from {trades_csv}")
    else:
        cat = build_catalog(args[0])
        trades = build_trades(cat, list(MICROS), stop_rule)
    days = sorted({tr["entry_day"] for tr in trades if tr["entry_day"].year >= START_YEAR})
    all_days = []
    d = days[0]
    while d <= days[-1]:
        if d.weekday() < 5: all_days.append(d)
        d += timedelta(days=1)
    starts = all_days[::5]                                     # one eval start a week
    os.makedirs(OUT, exist_ok=True)
    L = [f"# Prop firm simulation: {os.path.basename(trades_csv) if trades_csv else 'v2' + (' + stop rule' if stop_rule else '')} on CME micros"
         f"{' (holding through closes and weekends)' if not FLAT_AT_CLOSE else ''}"
         f"{' (no consistency rule)' if '--no-consistency' in args else ''}\n",
         f"{len(trades)} trades on {len(set(t['symbol'] for t in trades))} instruments, {len(starts)} eval start dates "
         f"(weekly, {starts[0]} to {starts[-1]}). Flat at the close and over weekends, re entry at 18:00 ET, "
         f"commissions and a tick each way. Risk fractions are of the plan's drawdown. Funded sizing drops to the "
         f"second fraction once profit exceeds one drawdown.\n"]
    console = ["", f"{'plan':16s} {'best eval risk':>14s} {'funded':>12s} {'pass':>5s} {'days':>5s} {'EV/attempt':>11s} {'EV/yr':>8s}"]
    for name in plans:
        P = PLANS[name]; best_rows = []
        L += [f"\n## {name}: {P.get('label', '')} | target {P['target']}, drawdown {P['dd']}, consistency "
              f"{P['consistency_eval']:.0%}\n",
              "| eval risk | funded risk (initial / after buffer) | pass rate | median days to pass | fees per pass | "
              "P(any payout) | payouts per funded acct | funded life (days) | EV per attempt | EV per year |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for er in EVAL_RISK:
            for fr, fa in FUNDED:
                recs = simulate_plan(P, trades, starts, er, fr, fa)
                passed = [r for r in recs if r["passed"]]
                pr = len(passed) / len(recs)
                fees = np.mean([r["fees"] for r in recs]); pay = np.mean([r["payouts"] for r in recs])
                ev = pay - fees
                med_days = np.median([r["days_to_pass"] for r in passed]) if passed else float("nan")
                dur = np.mean([(r["days_to_pass"] or MAX_EVAL_DAYS) + r["funded_days"] for r in recs])
                fpp = f"${fees / pr:,.0f}" if pr > 0 else "n/a"
                best_rows.append((ev, er, fr, fa, pr, med_days, ev * 365 / max(dur, 1)))
                L.append(f"| {er:.0%} | {fr:.0%} / {fa:.1%} | {pr:.0%} | {med_days:.0f} | {fpp} | "
                         f"{np.mean([r['payouts'] > 0 for r in passed]) if passed else 0:.0%} | "
                         f"${np.mean([r['payouts'] for r in passed]) if passed else 0:,.0f} | "
                         f"{np.mean([r['funded_days'] for r in passed]) if passed else 0:.0f} | ${ev:,.0f} | ${ev * 365 / max(dur, 1):,.0f} |")
                pass
        ev, er, fr, fa, pr, md, evy = max(best_rows)
        console.append(f"{name:16s} {er:>14.0%} {f'{fr:.0%} / {fa:.0%}':>12s} {pr:>5.0%} {md:>5.0f} {ev:>11,.0f} {evy:>8,.0f}")
    print("\n".join(console))
    L.append("\nEV per attempt = expected payouts (after split) minus expected fees, per eval started. EV per year assumes "
             "attempts run back to back. The strategy's edge here is close to zero after fills, so most of any positive "
             "EV is the firm absorbing the drawdown; check the consistency and payout rules against the firm's current terms.")
    open(os.path.join(OUT, "prop_report.md"), "w").write("\n".join(L) + "\n")
    print(f"\n-> {OUT}/prop_report.md")


if __name__ == "__main__":
    main()
