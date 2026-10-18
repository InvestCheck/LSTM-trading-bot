# Supply and demand zones on intraday bars (CME micro universe)

Rules, variants and the Notion log baseline are in the script header. Explore 2008 to 2014, validate 2015 to 2016, one holdout look per timeframe at the best validation config among the top 10 by exploration. Costs: commissions plus a tick on stop, BE and time exits. 'flat' = the same trades cut at 16:45 ET of the entry session (prop firm version).


## 5 minute bars: 4608 configs, 3456 with 300+ exploration trades; 10 positive on exploration, 0 positive on validation (flat version: 0 / 0)

| spike | cons | approach | manage | target | fresh | age | bias | parabolic | session | n explore | avgR explore | t | n validate | avgR validate | flat explore | flat validate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 1 | 1 | 2 | 0 | ny_am | 586 | +0.0289 | 0.35 | 157 | -0.0569 | -0.0341 | -0.0513 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 1 | 0 | 2 | 0 | ny_am | 587 | +0.0269 | 0.32 | 158 | -0.0292 | -0.0360 | -0.0325 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 1 | 1 | 2 | 1 | ny_am | 584 | +0.0218 | 0.26 | 157 | -0.0569 | -0.0414 | -0.0513 |
| 3.0 | 2.0 | 1.5 | fixed | nearest | 1 | 1 | 2 | 0 | ny_am | 596 | +0.0215 | 0.28 | 159 | -0.0575 | -0.0319 | -0.0520 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 1 | 0 | 2 | 1 | ny_am | 585 | +0.0198 | 0.24 | 158 | -0.0292 | -0.0433 | -0.0325 |
| 3.0 | 2.0 | 1.5 | fixed | nearest | 1 | 0 | 2 | 0 | ny_am | 597 | +0.0195 | 0.25 | 160 | -0.0302 | -0.0338 | -0.0334 |
| 3.0 | 2.0 | 1.5 | fixed | nearest | 1 | 1 | 2 | 1 | ny_am | 594 | +0.0145 | 0.19 | 159 | -0.0575 | -0.0391 | -0.0520 |
| 3.0 | 2.0 | 1.5 | fixed | nearest | 1 | 0 | 2 | 1 | ny_am | 595 | +0.0125 | 0.16 | 160 | -0.0302 | -0.0410 | -0.0334 |
| 3.0 | 2.0 | 1.5 | fixed | further | 1 | 1 | 2 | 0 | ny_am | 596 | +0.0071 | 0.09 | 159 | -0.0621 | -0.0484 | -0.0510 |
| 3.0 | 2.0 | 1.5 | fixed | further | 1 | 0 | 2 | 0 | ny_am | 597 | +0.0052 | 0.06 | 160 | -0.0252 | -0.0503 | -0.0325 |

Adam's stated config {'spike': 2.0, 'cons': 2.0, 'approach': 1.5, 'manage': 'be', 'target': 'nearest', 'fresh': 1, 'age': 0, 'bias': 1, 'parabolic': 1, 'session': 'all'}: explore 19730 trades avgR -0.2862 (t -19.94, win 18%), validate 5426 trades avgR -0.3089; flat version -0.2638 / -0.2978.

By entry hour (ET), stated config (holdout not read):

| hour | explore n | explore avgR | validate n | validate avgR |
|---|---|---|---|---|
| 00 | 1046 | -0.4000 | 314 | -0.4518 |
| 01 | 786 | -0.2255 | 201 | -0.3071 |
| 02 | 428 | -0.2862 | 117 | -0.0764 |
| 03 | 330 | -0.2105 | 86 | -0.1822 |
| 04 | 748 | -0.3267 | 200 | -0.4102 |
| 05 | 1330 | -0.1722 | 401 | -0.2370 |
| 06 | 1412 | -0.2905 | 417 | -0.4190 |
| 07 | 1157 | -0.3411 | 326 | -0.2890 |
| 08 | 583 | -0.2908 | 180 | -0.5689 |
| 09 | 554 | -0.1232 | 137 | -0.0470 |
| 10 | 741 | -0.0723 | 211 | -0.2718 |
| 11 | 1450 | -0.2053 | 412 | -0.3338 |
| 12 | 2425 | -0.2985 | 705 | -0.2054 |
| 13 | 2327 | -0.3327 | 644 | -0.3237 |
| 14 | 1471 | -0.3863 | 404 | -0.3770 |
| 15 | 1826 | -0.2851 | 407 | -0.1934 |
| 16 | 1112 | -0.3610 | 264 | -0.4314 |
| 18 | 4 | -1.0785 | 0 | +nan |

By entry hour (ET), chosen config:

| hour | explore n | explore avgR | holdout n | holdout avgR |
|---|---|---|---|---|
| 09 | 93 | +0.0063 | 83 | -0.1090 |
| 10 | 192 | -0.0750 | 213 | -0.3508 |
| 11 | 312 | +0.0541 | 419 | -0.2060 |

**Chosen {'spike': 3.0, 'cons': 2.0, 'approach': 1.5, 'manage': 'fixed', 'target': 'further', 'fresh': 1, 'age': 0, 'bias': 2, 'parabolic': 0, 'session': 'ny_am'}: holdout 2017 to 2026, 715 trades, net avgR -0.2379, t -3.31, win 26% -> no; flat version avgR -0.2274, t -3.72 -> no**

- exits by stop: 527 (74%), avgR -1.312
- exits by target (further): 188 (26%), avgR +2.772
- overnight holds: 13%; trades per instrument per year: 6; median bars held 7
- by year: 2017: -0.328 (n=70), 2018: -0.717 (n=58), 2019: -0.052 (n=43), 2020: -0.189 (n=72), 2021: -0.131 (n=72), 2022: +0.158 (n=94), 2023: +0.061 (n=86), 2024: -0.495 (n=83), 2025: -0.257 (n=83), 2026: -0.701 (n=54)
- by entry session: NY AM: -0.238 (n=715)
- fresh zones: -0.238 (n=715), tapped before: +nan (n=0); HTF with: -0.238 (n=715), HTF against or flat: +nan (n=0)

| instrument | trades | net avgR | t | win% | flat avgR |
|---|---|---|---|---|---|
| ES | 41 | +0.3636 | 1.17 | 32% | +0.3332 |
| NQ | 44 | -0.4814 | -1.99 | 16% | -0.4442 |
| RTY | 38 | -0.3854 | -1.37 | 21% | -0.3854 |
| GC | 64 | -0.2113 | -1.01 | 23% | -0.2508 |
| SI | 58 | -0.6333 | -3.35 | 12% | -0.4757 |
| HG | 83 | +0.1160 | 0.59 | 34% | +0.1053 |
| CL | 42 | -0.0371 | -0.12 | 29% | -0.1573 |
| NG | 79 | -0.1297 | -0.54 | 28% | +0.0477 |
| E6 | 77 | -0.3428 | -1.75 | 29% | -0.2925 |
| A6 | 63 | -0.4307 | -1.66 | 29% | -0.4593 |
| B6 | 39 | -0.0409 | -0.13 | 33% | -0.1677 |
| J1 | 63 | -0.7123 | -3.20 | 22% | -0.6910 |
| E1 | 24 | +0.1359 | 0.39 | 38% | -0.1162 |

NQ over the log window 2026-07-02 to 2026-10-16, stated config: engine 58 trades, avgR -0.029, win 19% (longs 25, shorts 33); log 128 taken trades, avgR +0.28 before costs. Trade list in sd_nq_logwindow_5m.csv.

## 15 minute bars: 4608 configs, 3314 with 300+ exploration trades; 23 positive on exploration, 16 positive on validation (flat version: 14 / 14)

| spike | cons | approach | manage | target | fresh | age | bias | parabolic | session | n explore | avgR explore | t | n validate | avgR validate | flat explore | flat validate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3.0 | 2.0 | 1.5 | fixed | further | 0 | 0 | 0 | 0 | ex_hours | 441 | +0.1315 | 1.16 | 115 | +0.1750 | +0.0981 | +0.1916 |
| 3.0 | 2.0 | 1.5 | fixed | further | 0 | 0 | 0 | 1 | ex_hours | 440 | +0.1250 | 1.10 | 115 | +0.1750 | +0.0916 | +0.1916 |
| 3.0 | 2.0 | 1.5 | fixed | further | 0 | 1 | 0 | 0 | ex_hours | 420 | +0.1229 | 1.09 | 108 | +0.1863 | +0.0878 | +0.1867 |
| 3.0 | 2.0 | 1.5 | fixed | further | 0 | 1 | 0 | 1 | ex_hours | 419 | +0.1160 | 1.04 | 108 | +0.1863 | +0.0809 | +0.1867 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 0 | 2 | 0 | ex_hours | 419 | +0.0771 | 0.81 | 116 | +0.0164 | +0.0389 | +0.0404 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 0 | 2 | 1 | ex_hours | 419 | +0.0771 | 0.81 | 116 | +0.0164 | +0.0389 | +0.0404 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 1 | 2 | 0 | ex_hours | 398 | +0.0731 | 0.73 | 103 | +0.1752 | +0.0467 | +0.1097 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 1 | 2 | 1 | ex_hours | 398 | +0.0731 | 0.73 | 103 | +0.1752 | +0.0467 | +0.1097 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 0 | 0 | 0 | ex_hours | 827 | +0.0686 | 0.92 | 225 | -0.0527 | +0.0156 | -0.0145 |
| 3.0 | 2.0 | 1.5 | fixed | rr1.5 | 0 | 0 | 0 | 1 | ex_hours | 826 | +0.0650 | 0.86 | 225 | -0.0527 | +0.0120 | -0.0145 |

Adam's stated config {'spike': 2.0, 'cons': 2.0, 'approach': 1.5, 'manage': 'be', 'target': 'nearest', 'fresh': 1, 'age': 0, 'bias': 1, 'parabolic': 1, 'session': 'all'}: explore 7837 trades avgR -0.2511 (t -12.62, win 18%), validate 2165 trades avgR -0.3501; flat version -0.2211 / -0.3223.

By entry hour (ET), stated config (holdout not read):

| hour | explore n | explore avgR | validate n | validate avgR |
|---|---|---|---|---|
| 00 | 941 | -0.2709 | 241 | -0.4737 |
| 01 | 1122 | -0.3474 | 309 | -0.3719 |
| 02 | 765 | -0.1183 | 217 | -0.3227 |
| 03 | 353 | -0.0655 | 77 | -0.1764 |
| 04 | 119 | -0.1680 | 31 | -0.0021 |
| 05 | 154 | -0.1540 | 34 | +0.1930 |
| 06 | 243 | -0.0259 | 76 | -0.5862 |
| 07 | 353 | -0.1991 | 101 | -0.1078 |
| 08 | 319 | -0.2123 | 117 | -0.3084 |
| 09 | 128 | -0.2320 | 59 | -0.4299 |
| 10 | 78 | -0.1397 | 26 | -0.1980 |
| 11 | 78 | -0.1771 | 27 | -0.3691 |
| 12 | 164 | -0.2296 | 53 | -0.0172 |
| 13 | 493 | -0.2804 | 149 | -0.4984 |
| 14 | 773 | -0.2950 | 217 | -0.4053 |
| 15 | 801 | -0.4019 | 210 | -0.4733 |
| 16 | 945 | -0.2490 | 219 | -0.2535 |
| 17 | 1 | -1.1957 | 0 | +nan |
| 18 | 7 | -0.6243 | 2 | -0.8275 |

By entry hour (ET), chosen config:

| hour | explore n | explore avgR | holdout n | holdout avgR |
|---|---|---|---|---|
| 04 | 420 | +0.1229 | 597 | -0.4439 |

**Chosen {'spike': 3.0, 'cons': 2.0, 'approach': 1.5, 'manage': 'fixed', 'target': 'further', 'fresh': 0, 'age': 1, 'bias': 0, 'parabolic': 0, 'session': 'ex_hours'}: holdout 2017 to 2026, 597 trades, net avgR -0.4439, t -5.34, win 19% -> no; flat version avgR -0.4419, t -5.69 -> no**

- exits by stop: 483 (81%), avgR -1.265
- exits by target (further): 114 (19%), avgR +3.036
- overnight holds: 3%; trades per instrument per year: 5; median bars held 4
- by year: 2017: -0.552 (n=44), 2018: -0.386 (n=65), 2019: -0.711 (n=62), 2020: -0.314 (n=82), 2021: -0.156 (n=62), 2022: -0.326 (n=30), 2023: -0.634 (n=60), 2024: -0.606 (n=66), 2025: -0.512 (n=59), 2026: -0.271 (n=67)
- by entry session: London 03:00-09:30: -0.444 (n=597)
- fresh zones: -0.531 (n=165), tapped before: -0.411 (n=432); HTF with: -0.481 (n=349), HTF against or flat: -0.392 (n=248)

| instrument | trades | net avgR | t | win% | flat avgR |
|---|---|---|---|---|---|
| ES | 57 | -0.5316 | -2.83 | 19% | -0.5316 |
| NQ | 43 | -0.9018 | -6.64 | 9% | -0.9018 |
| RTY | 54 | -0.1334 | -0.47 | 30% | -0.1334 |
| GC | 75 | -0.3432 | -1.52 | 17% | -0.3730 |
| SI | 64 | -0.3280 | -1.04 | 17% | -0.3783 |
| HG | 36 | -0.6602 | -2.54 | 14% | -0.5298 |
| CL | 28 | -0.0219 | -0.05 | 25% | -0.1809 |
| NG | 75 | -0.2618 | -1.17 | 21% | -0.2618 |
| E6 | 21 | -0.7577 | -1.85 | 10% | -0.6800 |
| A6 | 59 | -0.5441 | -2.06 | 22% | -0.5606 |
| B6 | 10 | +0.1772 | 0.19 | 30% | -0.0333 |
| J1 | 69 | -0.6928 | -2.58 | 17% | -0.5789 |
| E1 | 6 | -0.6597 | -1.09 | 17% | -0.6597 |

NQ over the log window 2026-07-02 to 2026-10-16, stated config: engine 14 trades, avgR -0.049, win 7% (longs 6, shorts 8); log 128 taken trades, avgR +0.28 before costs. Trade list in sd_nq_logwindow_15m.csv.
