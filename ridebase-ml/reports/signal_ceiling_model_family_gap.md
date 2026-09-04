# RideBase V1.5 Model-Family Gap Report

## 1. Executive Summary
To test whether the ~0.72-0.74 discrimination ceiling is an artifact of the continuous Cox proportional hazards objective rather than information limits, we evaluated four distinct survival learning architectures on out-of-sample VALIDATION.

### Performance Comparison Table
| Architecture | Objective / Formulation | Tier O2 (95 Obs) IPCW C | Tier O2 AUC (90d) | Tier M4 (Oracle) IPCW C | Tier M4 AUC (90d) |
|---|---|:---:|:---:|:---:|:---:|
| **XGBoost Cox PH** | `xgb_cox` | **0.7367** | 0.8204 | **0.7464** | 0.8310 |
| **XGBoost AFT (Log-Normal)** | `xgb_aft` | **0.7432** | 0.8247 | **0.7502** | 0.8327 |
| **Discrete-Time Hazard XGB (90d)** | `discrete_time_xgb` | **0.7299** | 0.8260 | **0.7393** | 0.8357 |
| **Penalized CoxNet (Linear)** | `coxnet` | **0.7254** | 0.8079 | **0.7319** | 0.8154 |

### Model-Family Gap Assessment
- **Best Learner on Observable Tier O2**: `XGBoost AFT (Log-Normal)` (IPCW C: `0.7432`)
- **Model Gap on O2 ($Best - XGB\_Cox$)**: `+0.006582`
- **Best Learner on Oracle Tier M4**: `XGBoost AFT (Log-Normal)` (IPCW C: `0.7502`)
- **Model Gap on M4 ($Best - XGB\_Cox$)**: `+0.003799`

### Conclusion
The model architecture gap on observable features is `+0.006582` (negligible, well below the predeclared 0.01 threshold). XGB-Cox and Discrete-Time XGB achieve virtually identical discrimination.
Therefore, **MODEL FAMILY GAP is NOT the primary bottleneck**. Changing the learner architecture will not unlock substantial ranking gains.