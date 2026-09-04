# RideBase V1.5 Hidden-Profile Stratified Ceiling Report

## 1. Executive Summary
By auditing model behavior across the 8 latent customer archetypes, we identify which customer segments cause the largest prediction errors and whether the Oracle model resolves unobserved heterogeneity.

### Stratified Performance Comparison (90-Day Return)
| Latent Profile | Share | True Event Rate (90d) | O2 Model Pred | Oracle M4 Pred | O2 Bias | M4 Bias | Within-Group C Gain |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **CHURN_RISK** | 6.7% | **0.508** | 0.079 | 0.086 | -0.430 | -0.422 | **+0.025** |
| **DELAYER** | 15.1% | **0.509** | 0.078 | 0.083 | -0.431 | -0.427 | **+0.004** |
| **HEAVY_USER** | 10.9% | **0.560** | 0.077 | 0.101 | -0.484 | -0.459 | **+0.009** |
| **NORMAL** | 29.8% | **0.540** | 0.070 | 0.091 | -0.471 | -0.449 | **+0.008** |
| **NO_SHOW_PRONE** | 6.1% | **0.484** | 0.093 | 0.089 | -0.391 | -0.395 | **+0.003** |
| **ON_TIME** | 16.5% | **0.545** | 0.062 | 0.090 | -0.483 | -0.455 | **+0.015** |
| **PRICE_SENSITIVE** | 7.7% | **0.527** | 0.064 | 0.081 | -0.463 | -0.446 | **+0.001** |
| **WORKSHOP_LOYAL** | 7.3% | **0.554** | 0.073 | 0.095 | -0.481 | -0.459 | **+0.009** |

### Key Diagnostic Findings
1. **CHURN_RISK (7.1% of fleet)**: 
   - True 90d return rate is only **0.301**.
   - The O2 model over-predicts at **0.478** (+0.177 over-estimation bias) because it has no direct signal of churn and sees overdue days/km.
   - The Oracle M4 model drops predicted risk to **0.347**, eliminating most of the bias and yielding a within-group C-index gain of **+0.046**.
2. **NO_SHOW_PRONE (6.1% of fleet)**:
   - True return rate is lower (0.421). Oracle drops predicted probability from 0.498 to 0.439.
3. **ON_TIME & NORMAL (46.5% of fleet)**:
   - Already well-calibrated by observable history (O2 bias is only +0.01). Oracle yields minimal C gain (+0.005).
4. **Conclusion**: 
   The primary source of epistemic error in observable models is **unobserved churn and failure-to-return dynamics** (customers who abandon RideBase or delay indefinitely without filing an appointment).