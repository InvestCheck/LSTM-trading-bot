# Two touch lines vs the frozen three touch engine

Each engine sequenced on its own (one position per instrument). v2 = cheap instrument and frozen tier score >= cutoff. '2 touch only' = trades the 2 touch engine took on lines with exactly 2 touches.

| set | gate | engine | trades | trades/yr | avgR | win% | total R/yr | boot t |
|---|---|---|---|---|---|---|---|---|
| explore | all | 3 touch | 7821 | 869 | +0.0224 | 48 | +19.4 | 1.37 |
| explore | all | 2 touch | 16378 | 1820 | +0.0132 | 50 | +23.9 | 0.99 |
| explore | all | 2 touch only | 9878 | 1098 | +0.0053 | 51 | +5.9 | 0.34 |
| explore | v2 | 3 touch | 2944 | 327 | +0.0995 | 49 | +32.5 | 3.64 |
| explore | v2 | 2 touch | 5318 | 591 | +0.0912 | 52 | +53.9 | 3.92 |
| explore | v2 | 2 touch only | 2971 | 330 | +0.0866 | 53 | +28.6 | 3.39 |
| holdout | all | 3 touch | 9622 | 982 | +0.0343 | 49 | +33.7 | 2.47 |
| holdout | all | 2 touch | 18385 | 1876 | +0.0262 | 51 | +49.1 | 2.47 |
| holdout | all | 2 touch only | 10131 | 1034 | +0.0179 | 52 | +18.6 | 1.59 |
| holdout | v2 | 3 touch | 3479 | 355 | +0.0786 | 48 | +27.9 | 3.70 |
| holdout | v2 | 2 touch | 5967 | 609 | +0.0705 | 51 | +42.9 | 4.46 |
| holdout | v2 | 2 touch only | 3052 | 311 | +0.0567 | 52 | +17.7 | 2.88 |

## Preregistered test (v2 gated)

Exploration: 2 touch only avgR +0.0866 t 3.39; total R/yr 2 touch +53.9 vs 3 touch +32.5 -> PASS
Holdout: 2 touch only avgR +0.0567 t 2.88; total R/yr 2 touch +42.9 vs 3 touch +27.9 -> PASS

Caveat: the tier model has never seen a 2 touch line; its touches weight is extrapolated. If 2 touch trades are positive ungated but the gate removes them, the right follow up is a refit with 2 touch trades in the fit, not a conclusion.

## Risk of the v2 gated books (daily mark to market, one unit of risk per trade)

| set | engine | Sharpe | max DD (R) | total R | daily vol (R) | open positions median / max | same cluster max | total R at the 3 touch book's vol |
|---|---|---|---|---|---|---|---|---|
| explore | 3 touch | 1.33 | 55.6 | +293 | 1.65 | 2 / 14 | 10 | +293 |
| explore | 2 touch | 1.44 | 75.9 | +486 | 2.21 | 4 / 23 | 13 | +362 |
| holdout | 3 touch | 1.06 | 43.1 | +273 | 1.73 | 3 / 14 | 10 | +273 |
| holdout | 2 touch | 1.11 | 50.7 | +420 | 2.24 | 4 / 23 | 15 | +324 |

| year | 3 touch total R | 2 touch total R | 3 touch max DD | 2 touch max DD |
|---|---|---|---|---|
| 2008 | +32 | +53 | 3 | 8 |
| 2009 | -22 | -20 | 56 | 76 |
| 2010 | +58 | +92 | 11 | 19 |
| 2011 | +35 | +45 | 12 | 23 |
| 2012 | +45 | +79 | 20 | 31 |
| 2013 | +62 | +84 | 13 | 12 |
| 2014 | +43 | +83 | 25 | 13 |
| 2015 | +30 | +24 | 14 | 15 |
| 2016 | +12 | +46 | 12 | 21 |
| 2017 | +1 | +10 | 18 | 17 |
| 2018 | +29 | +47 | 17 | 22 |
| 2019 | +58 | +68 | 10 | 13 |
| 2020 | +29 | +90 | 16 | 19 |
| 2021 | +8 | +27 | 38 | 34 |
| 2022 | +54 | +37 | 8 | 22 |
| 2023 | +33 | +54 | 20 | 21 |
| 2024 | +71 | +77 | 10 | 10 |
| 2025 | -10 | +2 | 36 | 43 |
| 2026 | -1 | +8 | 12 | 18 |

The last column scales the 2 touch book down to the 3 touch book's daily volatility: the fair comparison when risk per trade is set by a total risk budget rather than fixed per trade.

## Correlation with the S&P 500 (ES continuous contract returns)

| set | engine | daily corr | monthly corr | book R in ES's worst 10% months (avg per month) | book R in the other months | ES up months corr | ES down months corr |
|---|---|---|---|---|---|---|---|
| explore | 3 touch | -0.06 | -0.05 | +4.9 (n=11) | +2.6 | +0.04 | -0.25 |
| explore | 2 touch | -0.10 | -0.10 | +10.0 (n=11) | +4.0 | +0.11 | -0.04 |
| holdout | 3 touch | -0.12 | -0.04 | +7.1 (n=12) | +1.8 | +0.10 | -0.46 |
| holdout | 2 touch | -0.18 | -0.13 | +10.7 (n=12) | +2.8 | +0.12 | -0.56 |

| year | ES return (approx) | 3 touch R | 2 touch R | 3 touch daily corr | 2 touch daily corr |
|---|---|---|---|---|---|
| 2008 | -5% | +32 | +53 | -0.07 | +0.01 |
| 2009 | +3% | -22 | -20 | +0.25 | +0.25 |
| 2010 | +14% | +58 | +92 | -0.20 | -0.16 |
| 2011 | -14% | +35 | +45 | -0.31 | -0.49 |
| 2012 | +5% | +45 | +79 | -0.09 | -0.13 |
| 2013 | +24% | +62 | +84 | -0.01 | -0.12 |
| 2014 | +2% | +43 | +83 | -0.07 | -0.15 |
| 2015 | +9% | +30 | +24 | -0.19 | -0.27 |
| 2016 | +9% | +12 | +46 | +0.03 | -0.07 |
| 2017 | +14% | +1 | +10 | -0.11 | -0.22 |
| 2018 | -8% | +29 | +47 | -0.18 | -0.25 |
| 2019 | +25% | +58 | +68 | -0.01 | -0.08 |
| 2020 | -1% | +29 | +90 | -0.17 | -0.31 |
| 2021 | +23% | +8 | +27 | -0.20 | -0.20 |
| 2022 | -11% | +54 | +37 | -0.08 | -0.06 |
| 2023 | +19% | +33 | +54 | -0.02 | -0.07 |
| 2024 | +5% | +71 | +77 | -0.23 | -0.22 |
| 2025 | +11% | -10 | +2 | -0.15 | -0.16 |
| 2026 | -2% | -1 | +8 | -0.16 | -0.27 |

ES returns are on the back adjusted continuous series, so the level is approximate but the sign and ranking of months are right. A near zero correlation with a positive number in ES's worst months is the diversifying shape; a positive correlation means the book falls with stocks.
