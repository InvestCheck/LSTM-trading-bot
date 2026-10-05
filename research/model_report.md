# Tier model: pre order features, fit 2008 to 2016, ranked 2017 to 2026

Fit on 7821 trades, tested on 9622. Ridge 10.0. Threshold = exploration median score (+0.0239). One preregistered test, one sided z 1.64.

**Holdout, top half by score vs bottom half:** 4901 trades at +0.0665 vs 4721 at -0.0000, diff +0.0665, boot t 3.25 -> **PASS**

| holdout decile by score | n | avgR | win% |
|---|---|---|---|
| 1 (low) | 963 | -0.0142 | 48% |
| 2 () | 962 | -0.0455 | 48% |
| 3 () | 962 | +0.0081 | 52% |
| 4 () | 962 | +0.0174 | 50% |
| 5 () | 962 | +0.0306 | 51% |
| 6 () | 962 | +0.0460 | 50% |
| 7 () | 962 | +0.0579 | 50% |
| 8 () | 962 | -0.0024 | 45% |
| 9 () | 962 | +0.0380 | 47% |
| 10 (high) | 963 | +0.2023 | 51% |

| feature | weight (per std) |
|---|---|
| p_d_e200 | -0.0543 |
| inst_cost | -0.0424 |
| p_d_e50 | +0.0375 |
| p_room | +0.0368 |
| FX | +0.0330 |
| p_d_e21 | -0.0318 |
| hour_cos | -0.0264 |
| EQ | -0.0236 |
| sunday | -0.0210 |
| p_mom5 | -0.0194 |
| is_long | -0.0179 |
| touches | +0.0149 |
| p_atr_ratio | +0.0144 |
| ENERGY | -0.0129 |
| p_ext_1y | +0.0124 |
| log_span | -0.0113 |
| hour_sin | +0.0101 |
| AGS | -0.0081 |
| p_risk_atr | +0.0080 |
| p_mom20 | +0.0066 |
| METALS | +0.0056 |
| RATES | -0.0037 |
| stop_ema | +0.0000 |

Weights are the exploration fit; a weight only means something if the holdout test above passed.
