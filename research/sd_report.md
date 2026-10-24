# Supply and demand zones on intraday bars (CME micro universe)

Rules, variants and the Notion log baseline are in the script header. Explore 2008 to 2014, validate 2015 to 2016, one holdout look per timeframe at the best validation config among the top 10 by exploration. Costs: commissions plus a tick on stop, BE and time exits. 'flat' = the same trades cut at 16:45 ET of the entry session (prop firm version).


## 5 minute bars: 3456 configs, 2592 with 300+ exploration trades; 0 positive on exploration, 0 positive on validation (flat version: 0 / 0)

| spike | cons | approach | manage | target | fresh | age | bias | parabolic | session | n explore | avgR explore | t | n validate | avgR validate | flat explore | flat validate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.0 | 99.0 | 2.2 | fixed | nearest | 1 | 1 | 1 | 0 | ny_am | 9431 | -0.1394 | -9.22 | 2621 | -0.1625 | -0.1494 | -0.1572 |
| 2.0 | 99.0 | 2.2 | fixed | nearest | 1 | 0 | 1 | 0 | ny_am | 9496 | -0.1404 | -9.22 | 2631 | -0.1591 | -0.1501 | -0.1537 |
| 2.0 | 99.0 | 2.2 | fixed | nearest | 1 | 0 | 0 | 0 | ny_am | 13542 | -0.1439 | -10.48 | 3691 | -0.1702 | -0.1547 | -0.1656 |
| 2.0 | 99.0 | 2.2 | fixed | rr1.5 | 1 | 0 | 0 | 0 | ny_am | 12264 | -0.1444 | -8.86 | 3354 | -0.1797 | -0.1615 | -0.1706 |
| 2.0 | 3.0 | 2.2 | fixed | nearest | 1 | 1 | 1 | 0 | ny_am | 7287 | -0.1449 | -7.10 | 2026 | -0.1775 | -0.1683 | -0.1901 |
| 2.0 | 3.0 | 2.2 | fixed | nearest | 1 | 0 | 1 | 0 | ny_am | 7336 | -0.1449 | -7.08 | 2034 | -0.1759 | -0.1682 | -0.1893 |
| 2.0 | 99.0 | 2.2 | fixed | nearest | 1 | 1 | 0 | 0 | ny_am | 13432 | -0.1449 | -10.53 | 3671 | -0.1703 | -0.1554 | -0.1656 |
| 2.0 | 99.0 | 2.2 | fixed | nearest | 1 | 1 | 1 | 1 | ny_am | 9347 | -0.1450 | -9.58 | 2592 | -0.1614 | -0.1544 | -0.1587 |
| 2.0 | 99.0 | 2.2 | fixed | rr1.5 | 1 | 1 | 1 | 0 | ny_am | 8466 | -0.1454 | -8.04 | 2367 | -0.1573 | -0.1574 | -0.1488 |
| 2.0 | 99.0 | 2.2 | fixed | rr1.5 | 1 | 0 | 1 | 0 | ny_am | 8528 | -0.1457 | -8.04 | 2377 | -0.1533 | -0.1575 | -0.1450 |

Log derived config {'spike': 2.0, 'cons': 3.0, 'approach': 2.2, 'manage': 'be', 'target': 'nearest', 'fresh': 2, 'age': 0, 'bias': 0, 'parabolic': 1, 'session': 'all'}: explore 66918 trades avgR -0.2657 (t -33.57, win 23%), validate 18411 trades avgR -0.3118; flat version -0.2602 / -0.3071.

By entry hour (ET), log derived config:

| hour | explore n | explore avgR | validate n | validate avgR |
|---|---|---|---|---|
| 00 | 3139 | -0.3629 | 864 | -0.4336 |
| 01 | 2619 | -0.2355 | 683 | -0.3562 |
| 02 | 3043 | -0.3127 | 801 | -0.3345 |
| 03 | 3707 | -0.2910 | 1055 | -0.2664 |
| 04 | 3736 | -0.2600 | 1021 | -0.3834 |
| 05 | 3809 | -0.2950 | 1064 | -0.3458 |
| 06 | 3741 | -0.3022 | 1080 | -0.3233 |
| 07 | 4066 | -0.2546 | 1132 | -0.3714 |
| 08 | 4624 | -0.2488 | 1340 | -0.2981 |
| 09 | 5256 | -0.1760 | 1438 | -0.2308 |
| 10 | 5613 | -0.1843 | 1576 | -0.2388 |
| 11 | 5155 | -0.2348 | 1474 | -0.2747 |
| 12 | 4511 | -0.2328 | 1228 | -0.2510 |
| 13 | 4354 | -0.2749 | 1230 | -0.3492 |
| 14 | 4088 | -0.3083 | 1100 | -0.3010 |
| 15 | 3587 | -0.3583 | 856 | -0.3826 |
| 16 | 1856 | -0.3249 | 464 | -0.2476 |
| 18 | 13 | -1.2893 | 5 | -4.0988 |
| 20 | 1 | -0.6154 | 0 | +nan |

Log derived config: holdout sealed (exploration or validation not positive).

Chosen {'spike': 2.0, 'cons': 99.0, 'approach': 2.2, 'manage': 'fixed', 'target': 'rr1.5', 'fresh': 1, 'age': 0, 'bias': 1, 'parabolic': 0, 'session': 'ny_am'}: holdout sealed (exploration -0.1457, validation -0.1533, not both positive).

NQ over the log window 2026-07-02 to 2026-10-16, stated config: engine 199 trades, avgR -0.066, win 25% (longs 109, shorts 90); log 128 taken trades, avgR +0.28 before costs. Trade list in sd_nq_logwindow_5m.csv.

## 15 minute bars: 3456 configs, 2592 with 300+ exploration trades; 0 positive on exploration, 5 positive on validation (flat version: 0 / 0)

| spike | cons | approach | manage | target | fresh | age | bias | parabolic | session | n explore | avgR explore | t | n validate | avgR validate | flat explore | flat validate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.0 | 99.0 | 2.5 | fixed | further | 0 | 0 | 0 | 0 | ny_am | 14778 | -0.1148 | -6.88 | 4009 | -0.1336 | -0.1256 | -0.1515 |
| 2.0 | 99.0 | 2.2 | fixed | further | 0 | 0 | 0 | 0 | ny_am | 12485 | -0.1173 | -6.08 | 3387 | -0.1610 | -0.1202 | -0.1671 |
| 2.0 | 99.0 | 2.5 | fixed | further | 0 | 0 | 0 | 1 | ny_am | 14722 | -0.1189 | -7.11 | 3995 | -0.1431 | -0.1303 | -0.1593 |
| 2.0 | 99.0 | 2.2 | fixed | further | 0 | 0 | 0 | 1 | ny_am | 12445 | -0.1202 | -6.29 | 3377 | -0.1686 | -0.1238 | -0.1741 |
| 2.0 | 99.0 | 2.5 | fixed | nearest | 0 | 0 | 0 | 0 | ny_am | 14778 | -0.1222 | -8.78 | 4009 | -0.1148 | -0.1251 | -0.1476 |
| 2.0 | 99.0 | 2.2 | be | further | 0 | 0 | 0 | 0 | ny_am | 12485 | -0.1228 | -8.63 | 3387 | -0.1643 | -0.1277 | -0.1524 |
| 2.0 | 99.0 | 2.2 | fixed | rr1.5 | 0 | 0 | 0 | 0 | ny_am | 11182 | -0.1229 | -6.59 | 3039 | -0.1302 | -0.1221 | -0.1472 |
| 2.0 | 99.0 | 2.2 | fixed | nearest | 0 | 0 | 0 | 0 | ny_am | 12485 | -0.1239 | -7.64 | 3387 | -0.1332 | -0.1227 | -0.1520 |
| 2.0 | 99.0 | 2.2 | be | nearest | 0 | 0 | 0 | 0 | ny_am | 12485 | -0.1247 | -9.71 | 3387 | -0.1524 | -0.1278 | -0.1502 |
| 2.0 | 99.0 | 2.5 | fixed | rr1.5 | 0 | 0 | 0 | 0 | ny_am | 13257 | -0.1249 | -8.21 | 3605 | -0.1153 | -0.1298 | -0.1479 |

Log derived config {'spike': 2.0, 'cons': 3.0, 'approach': 2.2, 'manage': 'be', 'target': 'nearest', 'fresh': 2, 'age': 0, 'bias': 0, 'parabolic': 1, 'session': 'all'}: explore 28509 trades avgR -0.2080 (t -22.43, win 23%), validate 7823 trades avgR -0.2388; flat version -0.1975 / -0.2306.

By entry hour (ET), log derived config:

| hour | explore n | explore avgR | validate n | validate avgR |
|---|---|---|---|---|
| 00 | 1596 | -0.2382 | 437 | -0.2597 |
| 01 | 1746 | -0.2914 | 470 | -0.2556 |
| 02 | 2040 | -0.1889 | 621 | -0.3225 |
| 03 | 2099 | -0.2204 | 556 | -0.1082 |
| 04 | 1702 | -0.2080 | 450 | -0.2252 |
| 05 | 1522 | -0.1714 | 415 | -0.2031 |
| 06 | 1425 | -0.2577 | 361 | -0.1993 |
| 07 | 1587 | -0.1994 | 427 | -0.2685 |
| 08 | 1921 | -0.2251 | 559 | -0.1868 |
| 09 | 1867 | -0.1478 | 560 | -0.2459 |
| 10 | 2050 | -0.1621 | 564 | -0.3348 |
| 11 | 1901 | -0.1707 | 477 | -0.1086 |
| 12 | 1504 | -0.2044 | 395 | -0.2120 |
| 13 | 1305 | -0.1761 | 403 | -0.1938 |
| 14 | 1588 | -0.2022 | 429 | -0.2781 |
| 15 | 1403 | -0.2373 | 369 | -0.3677 |
| 16 | 1227 | -0.2816 | 326 | -0.3010 |
| 18 | 26 | +0.2514 | 4 | -1.0253 |

Log derived config: holdout sealed (exploration or validation not positive).

Chosen {'spike': 2.0, 'cons': 99.0, 'approach': 2.5, 'manage': 'fixed', 'target': 'nearest', 'fresh': 0, 'age': 0, 'bias': 0, 'parabolic': 0, 'session': 'ny_am'}: holdout sealed (exploration -0.1222, validation -0.1148, not both positive).

NQ over the log window 2026-07-02 to 2026-10-16, stated config: engine 56 trades, avgR +0.052, win 23% (longs 22, shorts 34); log 128 taken trades, avgR +0.28 before costs. Trade list in sd_nq_logwindow_15m.csv.
