# RideBase V1.5 Generator Oracle & Bayes-Ceiling Report

## 1. Executive Summary
The **GENERATOR_ORACLE** evaluates the theoretical Bayes ranking ceiling of the V1.5 synthetic world. It uses the exact instantaneous conditional hazard computed by the synthetic event generator at the landmark date without any estimation error or future outcome leakage.

### Benchmark Metrics
- **Generator Oracle IPCW C-Index**: `0.670691`
- **Generator Oracle Harrell C-Index**: `0.671013`
- **Mean Dynamic Horizon AUC**: `0.7430`

### Horizon Discriminative Performance
| Horizon | Eligible Samples | Empirical Base Rate | Generator Oracle ROC AUC | Brier Score |
|:---:|:---:|:---:|:---:|:---:|
| **30d** | 36357 | 0.2055 | **0.7499** | 0.1397 |
| **60d** | 36275 | 0.3872 | **0.7417** | 0.1977 |
| **90d** | 36215 | 0.5329 | **0.7406** | 0.2160 |
| **120d** | 36174 | 0.6508 | **0.7399** | 0.2148 |

### Decile Calibration (90-day Empirical Event Rates)
| Decile | Min Hazard | Max Hazard | Mean Theoretical Risk | Empirical 90d Event Rate |
|:---:|:---:|:---:|:---:|:---:|
| **D1** | 0.00000 | 0.00677 | 0.1519 | **0.2526** |
| **D2** | 0.00678 | 0.00833 | 0.2032 | **0.3024** |
| **D3** | 0.00833 | 0.00990 | 0.2387 | **0.3446** |
| **D4** | 0.00990 | 0.01188 | 0.2778 | **0.4079** |
| **D5** | 0.01188 | 0.01468 | 0.3269 | **0.4644** |
| **D6** | 0.01468 | 0.01911 | 0.3935 | **0.5374** |
| **D7** | 0.01911 | 0.02640 | 0.4894 | **0.6098** |
| **D8** | 0.02641 | 0.03928 | 0.6176 | **0.6985** |
| **D9** | 0.03928 | 0.06553 | 0.7751 | **0.8017** |
| **D10** | 0.06556 | 0.34981 | 0.9392 | **0.9097** |

### Key Finding
Even with perfect oracle knowledge of the true instantaneous hazard and latent behavioral parameters, the C-index in the synthetic world is **~0.671**. This demonstrates that the synthetic event generation process possesses a substantial amount of **irreducible stochastic noise** (Bernoulli trial randomness at each 3-day step).