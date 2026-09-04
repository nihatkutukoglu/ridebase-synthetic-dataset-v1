# RideBase V1.5 Information Ladder & Oracle Gap Report

## 1. Executive Summary
This evaluation applies the identical XGB-Cox survival learner recipe across 5 ascending information tiers on out-of-sample VALIDATION landmarks.

### Information Ladder Performance Table
| Tier ID | Information Tier | Features | IPCW C-Index | Harrell C-Index | IBS (30–120d) | Mean Dyn AUC | ECE (90d) |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **M0_O0** | Tier O0 (Core 54 Observable) | 54 | **0.727087** | 0.727261 | 0.396367 | 0.8003 | 0.4777 |
| **M1_O1** | Tier O1 (Extended 60 Observable) | 60 | **0.736649** | 0.736888 | 0.386154 | 0.8130 | 0.4664 |
| **M2_O2** | Tier O2 (Max 95 Observable) | 95 | **0.736747** | 0.736980 | 0.383007 | 0.8125 | 0.4628 |
| **M3_O2_L1** | Tier O2 + L1 (95 Obs + 7 Latent Stable) | 102 | **0.742967** | 0.743219 | 0.373594 | 0.8204 | 0.4527 |
| **M4_O2_L1_L2** | Tier O2 + L1 + L2 (110 Obs + Latent Dynamic) | 110 | **0.746963** | 0.747208 | 0.367108 | 0.8244 | 0.4452 |

### Temporal Slice Stability (IPCW C-Index)
| Tier ID | Jul–Aug Slice | Sep–Oct Slice | Nov–Dec Slice | Stable? |
|---|:---:|:---:|:---:|:---:|
| **M0_O0** | 0.7452 | 0.7248 | 0.7122 | PASS |
| **M1_O1** | 0.7543 | 0.7343 | 0.7220 | PASS |
| **M2_O2** | 0.7542 | 0.7346 | 0.7218 | PASS |
| **M3_O2_L1** | 0.7612 | 0.7420 | 0.7263 | PASS |
| **M4_O2_L1_L2** | 0.7651 | 0.7456 | 0.7308 | PASS |

### Information Gap Decomposition
- **Observable Feature Gain ($M_2 - M_1$)**: `+0.000098` (95 vs 60 observable features)
- **Latent Stable Gap ($M_3 - M_2$)**: `+0.006220` (adding 7 true customer behavioral traits)
- **Latent Dynamic Gap ($M_4 - M_3$)**: `+0.003996` (adding dynamic churn status & step hazards)
- **TOTAL ORACLE GAP ($M_4 - M_2$)**: `+0.010216`
- **IBS Improvement ($M_2 	o M_4$)**: `+0.015899`