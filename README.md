# Trendline breakout engine, futures

**Retraction (September 2026).** The result this repository first reported, [HEADLINE: e.g. "+0.XXR per trade across 131 instruments, 2008 to 2026"], was wrong and is withdrawn. A reader pointed out a look ahead in the fill logic; the audit that followed found three more defects. Corrected and multiplicity adjusted, the full sample selection stage found no instrument clearing a Bonferroni threshold of t > 3.55, and the stage 2 holdout selected nothing. What remains is a small pooled edge that is now being measured the only honest way left: a pre registered, six month paper forward test on an IBKR account, running since 16 October 2026. Everything below is in service of that test.

## What was wrong

| defect | effect |
|---|---|
| Non causal pivot detector | lines were drawn with knowledge of bars after the pivot |
| Unrealistic entry fill | entries assumed at the line price on the breaking bar, with no path check |
| Missing tick table | costs understated on the instruments with large ticks relative to range |
| Price rounding in storage | [76% of the best single instrument result] came from rounding, not price |

Each one inflated results on its own, and they compounded. The audit tools are in the repo (`stats_honest.py`, `holdout_stage2.py`, `span_sweep.py`, `tick_sanity.py`, `stop_width.py`, `filter_control.py`, `jackknife.py`, `commission_sensitivity.py`) and the dated commits show the order in which each defect was found and fixed.

## What the audit left standing

- No per instrument claim. Nothing clears t > 3.55 full sample, and the holdout selection returned empty. That result stands.
- A pooled hypothesis only: the trendline walk signal, equal risk across the executable universe at a long span floor, has a positive per trade edge net of realistic costs. Backtest estimate after all corrections: [+0.0XR per trade at engine prices, +0.03 to +0.05R at the resting order line], far too small to trust without new data.
- The full history (2008 to 2026, 131 instruments) has been used for selection, contamination analysis, span sweeps and four rounds of defect hunting. There is no clean slice of it left. Forward data is the only unspent data this project has.

## What is running now

`forward_test_protocol.md` was committed before the first paper trade and freezes the configuration, the universe (70 instruments, 68 executable at IBKR), the data vintage (sha256 recorded), the roll rules, the cost model and the stopping rule: minimum six months or 400 trades, whichever is later, no early stop for any reason. Protocol v2 (`protocol_v2.md`) adds a cost cap and a frozen tier cut, fitted on 2008 to 2016 only.

- Execution: resting stop orders at the line, intrabar, one contract per trade, on a DigitalOcean droplet talking to IBKR paper (`live_ibkr.py`). Every order, fill, roll and reconciliation is logged with a timestamp; each trade row carries the engine assumed price and the actual fill.
- Scoring: R per trade on actual fills, against a pre set benchmark band. A good six months does not raise the estimate, it only confirms the sign.
- Pre registration: `research/v3_preregistration.md` lists every follow up idea with its one test and adopt rule, written before the forward data existed, and an incident log. The 2017 to 2026 holdout is treated as spent and is read once more, in April 2027, for the items named there.
- Read out: April 2027. Until then nothing about the strategy changes; operational fixes are logged in the incident log and deployed with the markets closed.

## Why keep a repository of a retracted result

Because the retraction is the result. The feedback loop that caught it, outside reader, audit, second defect, withdrawal, pre registered forward test, is the only process that produces a number worth trading, and a dated public build log is the only evidence that the process happened. If the forward test comes back negative that goes here too, at the top.

## Layout

```
backtest_hull.py            engine (frozen at the protocol commit)
batch_backtest.py           universe runs
live_ibkr.py                forward test runner, IBKR paper
forward_test_protocol.md    frozen configuration and stopping rule
protocol_v2.md              cost cap and tier cut, fitted 2008 to 2016
research/                   studies, each with its report; v3_preregistration.md
backtests/                  trade files regenerated from the archived data vintage
```
