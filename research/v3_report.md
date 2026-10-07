# v3 candidates on top of v2: explored 2008 to 2016, tested once on 2017 to 2026

Base = v2 (cost cap + tier cut). 2944 exploration trades, 3479 holdout trades. 9 preregistered holdout tests, one sided z **2.54**. Costs 2 ticks per round trip. Sizing quartile threshold and combo_B membership were fixed on the exploration half.

combo_A = stop_rule + chandelier. combo_B = exploration positives = stop_rule + chandelier + sizing + cluster_cap.

## Exploration half (for choosing, not for deciding)

| candidate | effect | t | detail |
|---|---|---|---|
| base | +0.0975 | 3.24 | 2944 trades, 341/yr, avgR +0.0975, +33.3 R/yr, Sharpe 1.34 |
| stop_rule | +0.1196 | 2.90 | in 1151 at +0.1703, out 1793 at +0.0508; in only: +22.7 R/yr |
| session | -0.0074 | -0.13 | in 1729 at +0.0945, out 1215 at +0.1018; in only: +18.9 R/yr |
| chandelier | +0.0146 | 0.53 | paired diff +0.0146 on 2944; Sharpe 0.92 |
| retest | -1.0734 | -4.22 | 2519 of 2944 retested, avgR +0.0234, +6.8 R/yr; Sharpe 1.34 -> 0.27 |
| pyramid | -0.3373 | -5.44 | 123 adds, add avgR +0.2845; Sharpe per unit 1.34 -> 1.00 |
| sizing | +0.1177 | 1.47 | top quartile x1.5; Sharpe 1.34 -> 1.46 |
| cluster_cap | +0.1287 | 2.06 | skips 170 of 2944 (avgR of skipped +0.0410); Sharpe 1.34 -> 1.47 |

## Holdout 2017 to 2026 (the preregistered tests)

| test | effect | t | verdict | detail |
|---|---|---|---|---|
| base | +0.0777 | 3.77 | reference | 3479 trades, 359/yr, avgR +0.0777, +27.9 R/yr, Sharpe 1.07 |
| stop_rule | +0.1380 | 2.91 | PASS | in 1384 at +0.1609, out 2095 at +0.0228; in only: +23.0 R/yr |
| session | +0.0725 | 2.24 | no | in 1946 at +0.1097, out 1533 at +0.0372; in only: +22.0 R/yr |
| chandelier | +0.0510 | 1.99 | no | paired diff +0.0510 on 3479; Sharpe 1.25 |
| retest | -1.2735 | -5.00 | no | 2997 of 3479 retested, avgR -0.0141, -4.4 R/yr; Sharpe 1.08 -> -0.20 |
| pyramid | -0.3252 | -5.55 | no | 144 adds, add avgR +0.1670; Sharpe per unit 1.08 -> 0.75 |
| sizing | +0.0933 | 1.78 | no | top quartile x1.5; Sharpe 1.08 -> 1.17 |
| cluster_cap | +0.0399 | 0.38 | no | skips 290 of 3479 (avgR of skipped +0.0633); Sharpe 1.08 -> 1.12 |
| combo_A | +0.0462 | 0.19 | no | stop_rule+chandelier: Sharpe 1.08 -> 1.12 |
| combo_B | +0.1247 | 0.55 | no | stop_rule+chandelier+sizing+cluster_cap: Sharpe 1.08 -> 1.20 |

Effect units: avgR difference for stop_rule, session, chandelier; Sharpe difference for retest, pyramid, sizing, cluster_cap and the combos. The stop rule, session and chandelier are on their third look at this holdout; weigh a PASS there accordingly.
