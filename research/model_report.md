# Tier model: pre order features, fit 2008 to 2016, ranked 2017 to 2026

Fit on 7821 trades, tested on 9622. Ridge 10.0. Threshold = exploration median score (+0.0241). One preregistered test, one sided z 1.64.

**Holdout, top half by score vs bottom half:** 4874 trades at +0.0572 vs 4748 at +0.0099, diff +0.0472, boot t 2.33 -> **PASS**

| holdout decile by score | n | avgR | win% |
|---|---|---|---|
| 1 (low) | 963 | -0.0128 | 47% |
| 2 () | 962 | -0.0519 | 48% |
| 3 () | 962 | +0.0537 | 53% |
| 4 () | 962 | -0.0098 | 49% |
| 5 () | 962 | +0.0558 | 51% |
| 6 () | 962 | +0.0271 | 49% |
| 7 () | 962 | +0.0688 | 50% |
| 8 () | 962 | +0.0194 | 47% |
| 9 () | 962 | +0.0728 | 47% |
| 10 (high) | 963 | +0.1154 | 49% |

| feature | weight (per std) |
|---|---|
| p_d_e200 | -0.0608 |
| p_d_e50 | +0.0449 |
| p_d_e21 | -0.0407 |
| inst_cost | -0.0407 |
| FX | +0.0338 |
| p_room | +0.0315 |
| hour_cos | -0.0261 |
| EQ | -0.0238 |
| sunday | -0.0205 |
| p_mom5 | -0.0192 |
| is_long | -0.0180 |
| ENERGY | -0.0138 |
| touches | +0.0121 |
| p_atr_ratio | +0.0119 |
| log_span | -0.0113 |
| hour_sin | +0.0099 |
| p_ext_1y | +0.0098 |
| p_risk_atr | +0.0094 |
| AGS | -0.0089 |
| METALS | +0.0060 |
| p_mom20 | +0.0045 |
| RATES | -0.0031 |
| stop_ema | +0.0031 |

Weights are the exploration fit; a weight only means something if the holdout test above passed.
