# RideBase V1.5 Observability Recovery Analysis

## Executive Summary
This analysis evaluates how well the maximum legitimate observable history (Tier O2 — 95 features) can identify hidden behavioral traits (Tier L1) and landmark dynamic states (Tier L2) on out-of-sample VALIDATION landmarks.

### Observability Recovery Table
| Latent State | Best Observable Proxy | Out-of-Sample R² / AUC | Rank Correlation (Spearman) | Identifiability Status |
|---|---|---|---|---|
| **Adherence Tendency** | `historical_service_delay_mean_days (|rho|=0.331)` | 0.3026 | 0.4527 | `PARTIAL` |
| **No-Show Propensity** | `prior_no_show_count (|rho|=0.329)` | 0.2418 | 0.3679 | `PARTIAL` |
| **Churn Propensity** | `no_show_rate (|rho|=0.054)` | 0.1536 | 0.2144 | `WEAK` |
| **Workshop Loyalty** | `is_fleet_customer (|rho|=0.153)` | 0.1482 | 0.3548 | `WEAK` |
| **Price Sensitivity** | `days_since_last_breakdown (|rho|=0.035)` | 0.1359 | 0.3565 | `WEAK` |
| **Customer Frailty** | `recent_service_count_365d (|rho|=0.077)` | 0.1355 | 0.3504 | `WEAK` |
| **Already Churned at Landmark** | `Full GBDT on O2` | N/A (binary) | AUC=0.331 | `EFFECTIVELY_UNOBSERVABLE` |

### Archetype Identification (Macro-F1: 0.434)
| Latent Archetype | Out-of-Sample OvR AUC | Recovery Status |
|---|---|---|
| **CHURN_RISK** | 0.8276 | `PARTIAL` |
| **DELAYER** | 0.7865 | `PARTIAL` |
| **HEAVY_USER** | 0.8013 | `PARTIAL` |
| **NORMAL** | 0.7731 | `PARTIAL` |
| **NO_SHOW_PRONE** | 0.8563 | `RECOVERABLE` |
| **ON_TIME** | 0.7861 | `PARTIAL` |
| **PRICE_SENSITIVE** | 0.8277 | `PARTIAL` |
| **WORKSHOP_LOYAL** | 0.8103 | `PARTIAL` |

### Core Findings
- **No-Show Propensity**: Has weak-to-partial observability (`no_show_rate`, `prior_no_show_count`) with R² around +0.07 to +0.15.
- **Adherence Tendency**: Moderate recovery from `recency_weighted_adherence_score` and historical delay ratios.
- **Churn Propensity & State**: Severely unobservable (R² < 0.05, AUC ~ 0.58). The observable tables lack direct signals of customer departure or off-platform servicing.
- **Price Sensitivity & Frailty**: Effectively unobservable (R² ~ 0.00). Unobserved frailty cannot be separated from random arrival noise.