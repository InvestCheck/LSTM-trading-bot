# v3 pre registration

Written 24 October 2026, eight days into the paper run. Frozen from this commit.
Nothing below is decided before the paper run ends (first paper fill 16 October 2026 plus
six months, so mid April 2027). The 2017 to 2026 holdout has been read about a dozen times
and is treated as spent: it is read once more, in April, for the items that say so, and
never again after that.

## What runs until April

- Paper bot: protocol v2 (cost cap 0.05R, frozen tier cut), one contract, resting at the
  deeper line. Untouched.
- v1 shadow inside the bot (engine_trade rows).
- 2 touch shadow: `shadow_touch2.py`, daily 22:25 UTC, logs every closed 2 touch engine
  trade at engine prices with v2 flag, stop size in ATR, ADX(14) at entry. Started
  24 October 2026 with watermarks at the last cached bar; nothing before that date counts.

## Benchmarks the paper run is scored against (set now)

| book | per trade at engine prices | per trade at the deeper line | trades per year |
|---|---|---|---|
| v2 (3 touch) | +0.079R | +0.027R (placement sim) to +0.048R (1 minute study) | 355 |
| v2 + stop rule | +0.166R | +0.102R | about 120 |
| v2, 2 touch | +0.071R | +0.034R | 609 |

Fill vs engine on the first 7 paper fills averaged +0.20R worse (refit moved the line);
the long run figure in the placement study is +0.019R. The paper run's own average is
reported in April next to both.

## Decisions in April, one test each

Statistic unless stated: avgR with a block bootstrap over calendar quarters (months for the
paper data), one sided z 1.64. "Fresh data" = paper fills and shadow rows from 16 or 24
October 2026 onward.

1. **Edge at the line.** Paper fills, actual prices, all v2 trades. Decision rule: trade
   real money only if the paper avgR is positive and within one bootstrap standard error of
   the +0.027R to +0.048R band, and fill vs engine averaged under 0.06R. Otherwise another
   six months on paper.
2. **Stop rule (stop ≤ 2.5 ATR).** Subset of the paper fills. Adopt if its avgR exceeds the
   full v2 paper avgR; it was +0.166R vs +0.083R on the holdout, so a reversal on fresh data
   is the only thing that stops it.
3. **Two touch lines.** Shadow rows, v2 flagged. Adopt if the shadow avgR is positive and
   the 2 touch only subset (touches = 2) is not worse than the 3 touch subset by more than
   one standard error. Holdout reference: +0.071R all, +0.057R two touch only, t 2.88.
   Adoption means the executed engine moves to min touches 2 **and** live sizing carries a
   cluster cap, because the 2 touch book holds up to 23 positions and 15 in one cluster.
4. **ADX ≤ 20 at entry.** Shadow rows and paper fills (ADX computed from the cache for the
   paper fills). Not a filter: it keeps 29% of trades and drops total R. Adopt as a sizing
   tilt (item 9 below) if the ADX ≤ 20 subset's avgR exceeds the rest on fresh data.
   Holdout reference: +0.158R vs +0.042R inside v2, t 2.95.
5. **Chandelier 3 ATR exit.** Scored on paper fills from the cache against the engine exit,
   paired. Adopt if paired difference is positive with t > 1.64 on fresh data, else drop
   for good. Holdout reference: +0.07R in the stop subset, t 1.59, third positive look.
6. **Tier model refit.** After April only, one fit on 2008 to 2016 with 2 touch trades in
   the training set and ADX, breadth and S&D zone distance (nearest mechanical zone ahead
   and behind in ATR) as added features; one read of the holdout, top half vs bottom half
   inside v2. If it does not beat the frozen model's split by more than one standard error
   the frozen model stays.
7. **Collapse full and mini pairs** (GC/MGC, E6/E7, J1/J7, FDAX/FDXM): design decision, no
   test; one position per market when live sizing is written.
8. **Stop limit entries:** decided on paper fills, adopt only if more than 10% of fills were
   worse than the trigger by over 3 ticks.
9. **Conviction sizing:** after April, with ADX bucket and tier score as inputs, simulated on
   exploration years, one holdout read together with item 6.
10. **Cluster cap:** required under 2 touch; the cap level (3 or 4 per asset class) chosen on
    exploration years only, no holdout read.

## Killed, not to be reopened

Retest entry; 1 minute confirmation; pyramiding; rest at the refit line and gap aware
hybrids (killed again at 2 touch); four touch lines; band fade; half off at 1R; removing the
parabolic; equity exclusion; shorts only; hour of day and session filters; VWAP fades;
intraday engine on prop firms; prop firm deployment and the zero edge option thesis; S&D
automation on every instrument; stop caps and stop fractions 0.5× to 2× (nothing beats the
engine stop in R); momentum confluence (MACD, RSI, EMA slope, higher timeframe trend,
breadth, all flat or negative); vol targeting (lower drawdown, no Sharpe); tier refit with
ADX and breadth on 3 touch trades only (passes but adds 0.025R over the frozen model).

## Findings worth keeping in mind

- Two things survived out of about twenty five and they say the same thing: breaks out of
  tight, quiet conditions work (stop ≤ 2.5 ATR, ADX ≤ 20); breaks with momentum behind them
  are late.
- The book is uncorrelated with equities on average (daily corr −0.12 to −0.18 on the
  holdout) and negatively correlated when equities fall (−0.46 to −0.56 in ES down months);
  it made +7R to +11R per month in ES's worst 10% of months. Its own bad year (2009) was a
  stock rally off a bottom. Twelve worst months is a small sample.
- Risk at one unit per trade, 2 touch v2 holdout: 43R per year at engine prices, 51R max
  drawdown, Sharpe 1.11. Plan live on 1.5× the historical drawdown.

## Rules

- No new holdout read before April, and in April only the reads listed above.
- No change to the paper bot's code or configuration until the run ends.
- Any idea that comes up before April is appended here with its test, not run.
