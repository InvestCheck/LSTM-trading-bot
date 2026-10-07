# Forward test protocol v2

**Commit this file, `tier.py`, `v2_config.json` and `research/tier_model.json`
before the first v2 fill.** Same rule as v1: if the commit is not older than the
first executed trade, the v2 result is discarded.

## Relationship to v1

v1 (`forward_test_protocol.md`) stays the frozen primary test. Nothing in it
changes: same engine, same configuration, same 70 instrument universe, same
data vintage, same costs, same pass criteria. Both protocols run in **one
process on one paper account**:

- Every v1 signal is still generated and logged. The v1 verdict is scored on
  engine prices from the `engine_trade` rows in `trade_log.csv`, exactly as v1
  specifies, so v1 does not need fills.
- Orders are sent only for the signals v2 would take. v2 is scored on those
  executed trades with their real fills.

What v1 gives up: fill data on the signals v2 skips. Accepted.

## Execution (applies to both)

Resting order execution, `live_ibkr.py` with `EXEC=resting`, `entry_scan.py`:

```
at each bar close     for each line that passes the engine's refit geometry and
                      has a valid engine stop on data through that bar, rest a
                      stop order at the level the next bar would have to touch
                      (one per direction per instrument, OCA, provisional stop
                      attached)
fill                  at the line, intrabar, like the backtest
next close            engine runs; signal present -> CONFIRMED, stop becomes the
                      engine's; signal absent -> SCRATCHED at market
unfilled              cancelled and re-placed at the new levels
```

On 2008 to 2026 this recovers the backtest's edge: 99% of prequalified touches
confirmed, +0.061 ATR per touch net of scratches (`research/intrabar/report.md`).
Entering at the next bar's open instead loses about 0.07R per trade, which is
the entire edge; that finding is why execution works this way.

## v2 rules (which signals are executed)

A v1 signal is executed if and only if both hold at order placement:

```
1. cost cap     instrument's average round trip cost <= 0.05R, measured on the
                data vintage with 2 ticks per round trip (v2_config.json).
                43 of 70 qualify; MFS and MME are not listed at IBKR, so 41
                are executable. The list is frozen in v2_config.json.
2. tier cut     tier score >= the cutoff stored in research/tier_model.json.
                Score = frozen ridge fit on 2008 to 2016 trades, pre order
                features only (previous bar EMA distances, momentum, room to
                the band, extreme distance, ATR ratio, stop size, span,
                touches, direction, stop source, hour, Sunday, instrument
                cost, asset class). Cutoff = median score of the fit set.
```

Evidence for the tier cut: on the 2017 to 2026 holdout the top half by score
made +0.067R per trade against 0.000R for the bottom half, bootstrap t 3.25
(`research/model_report.md`). The holdout was examined twice (once before a
robustness fix to the features), so this is reported as "passes comfortably",
not as a single clean test.

The cost cap is a cost rule, the same kind v1 uses at 10%, tightened. As a
performance rule it did not clear its holdout bar (t 1.83); it is included
because the instruments it removes were net negative after costs on the full
sample (gross +0.12R, net -0.05R).

Not included: the stop size rule (initial stop within 2.5 ATR), holdout t 2.30
against a bar of 2.45. Parked for v3.

## Execution realism, measured before the run (October 2026)

Two studies on the 2017 to 2026 v2 trades, both committed on `research`:

- `research/1m_report.md`: the 1 minute path through each entry hour. A stop
  order at the bot's trigger fills at the line or better in 62% of entries, but
  20% of fills are more than 5 ticks through it, and those fast breaks are the
  best trades on paper. A stop limit does not help (keeping only the slow fills
  is worse).
- `research/placement_report.md`: resting at the refit line instead of the
  deeper line recovers the engine's price but turns one touch in four into a
  scratch; net worse. Placement stays at the deeper line.

Per trade, holdout 2017 to 2026:

| | v2 | v2 + stop rule |
|---|---|---|
| engine (backtest) | +0.083R | +0.166R |
| at the deeper line, no slippage (what IBKR paper fills will show) | +0.048R | +0.102R |
| realistic stop fill (mid of the breach minute) | +0.019R | +0.051R |

**IBKR's paper engine fills stop orders at the trigger, so the paper run will
look like the middle row, not the bottom row.** The bottom row is the honest
expectation for real money and is recorded here so the paper result is not
mistaken for it.

## v3 hypothesis, scored as a subset of this run

Stop size rule: initial stop within 2.5 ATR of entry. Preregistered and tested
three times on the 2017 to 2026 holdout (t 2.30, then 2.91 on the v2 base,
`research/v3_report.md`); it also holds up best under realistic fills. It is
NOT applied to execution, so the run keeps the fill data on every v2 trade;
every `confirm` and `engine_trade` row records the stop size in ATR, and the
v2 + stop rule result is scored from those rows as a subset, with the same
categories as v2.

## Scoring v2

Scored set: trades the bot executed, as logged at the time (`confirm` and
`exit` rows). Scratches count: a filled order the engine did not confirm is an
execution cost and its P&L is included. An engine signal that produced no fill
(`missed_fill`) is not a trade and is reported as a count.

R per trade uses the actual fill and actual exit, net of actual commissions.
Engine R is reported alongside for the same trades.

Categories, identical to v1, on the pooled executed set with the calendar
quarter block bootstrap:

- **PASS**: net avgR > 0 and pooled t > 2.0
- **INCONCLUSIVE**: net avgR > 0 and pooled t <= 2.0
- **FAIL**: net avgR <= 0

### Expected outcome, stated in advance

Holdout numbers for the executed subset point to roughly 350 trades a year,
about 175 in six months, at a net avgR in the region of +0.05 to +0.09R. That
gives a pooled t of roughly 0.7 to 1.2. **The most likely outcome is
INCONCLUSIVE for v2 as well as for v1.** Six months is a calibration run and a
record, not a verdict; a decisive answer on this edge needs 12 to 24 months.
This is recorded so an INCONCLUSIVE reads as predicted, and so the run is not
extended until something crosses a threshold.

Fills are the other thing this run measures. Paper stop fills at the line are
kinder than real ones in fast markets; the gap between paper fills and the
engine price, and the scratch rate, are reported as their own numbers.

## Duration and stopping rule

Six months from the first v2 fill, or 150 executed trades, whichever is later.
v1 is scored over the same window. No early stop for any reason. Operational
gaps are logged and extend the clock; nothing is backfilled.

## Sizing

One contract per trade, every executed signal, no scaling. Position sizing
by score (full size top tier, reduced below) was considered and rejected in
favour of the cut: on the holdout the bottom half earns nothing, so it is
dropped rather than sized down.

## What gets published

Both results, v1 and v2, at the same prominence, whatever they show, plus the
fill statistics. If v2 is FAIL and v1 is not, the executed subset was a
mistake and the honest summary says so.

## Parked (positive on the holdout, not significant; the forward run is their holdout)

- Chandelier 3 ATR trail as the exit (paired t 1.99)
- Day session only, 08:00 to 16:59 ET (t 2.24)
- Conviction sizing, 1.5 units on the top score quartile (Sharpe +0.09, t 1.78)
- Cluster cap, at most 3 concurrent trades per asset class (t 0.38)
- Nonlinear or yearly refit tier model (untested)

Killed on the holdout (`research/v3_report.md`, `research/1m_report.md`,
`research/placement_report.md`): retest entry, pyramiding, 1 minute
confirmation entry, resting at the refit line. Killed earlier: band fade,
equity index exclusion, shorts only, four touch lines, half off at 1R,
removing the parabolic exit.

---

**Committed:** _(commit hash and date of this file, tier.py, v2_config.json and
research/tier_model.json, filled in before the first v2 fill)_
