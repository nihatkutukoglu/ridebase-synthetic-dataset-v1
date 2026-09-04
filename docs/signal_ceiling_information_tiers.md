# RideBase V1.5 Signal Ceiling & Oracle Gap Study: Information Tiers

## Overview
This document defines the formal hierarchy of information tiers used in the RideBase V1.5 Signal Ceiling and Oracle Gap diagnosis study.

The goal is to determine whether the ~0.72 C-index plateau is driven by:
1. **Missing Observable Signal**: Key behavioral states exist in the generator but are unobservable in standard operational tables.
2. **Generator Stochasticity / Irreducible Noise**: The future event process is fundamentally noisy even conditioned on the true latent state.
3. **Model Family / Estimation Gap**: The XGB-Cox learner fails to extract available non-linear survival signals.

---

## Hierarchy of Information Tiers

```
┌────────────────────────────────────────────────────────────────────────┐
│ TIER H: True Generator Hazard / Propensity Oracle                      │
│ (Instantaneous conditional hazard and analytic return rate at landmark)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ TIER L2: Landmark Latent Dynamic State Oracle                          │
│ (Generator dynamic state: churn status, missed friction, step hazards) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ TIER L1: Latent Stable Behavior Oracle                                 │
│ (Customer hidden behavioral traits: adherence, loyalty, frailty, etc.) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ TIER O2: Maximum Observable History (V2.3 — 95 features)               │
│ (Point-in-time adherence trends, appointment metrics, usage velocity)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ TIER O1: Extended Observable (V2.2 EXTENDED60 — 60 features)           │
│ (Core 54 + 6 appointment & recency signals)                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ TIER O0: Core Observable Baseline (V2.1 Frozen — 54 features)          │
│ (Original frozen history contract)                                     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Tier Specifications

### Tier O0 — Core Observable (V2.1 Frozen 54 Features)
- **Feature Count**: 54
- **Origin**: Frozen V2.1 contract (`ridebase-ml/models/v2_1_v1_4/feature_list.json`)
- **Semantic Content**: Static bike/customer attributes, basic odometer readings, days/km since last service, OEM policy intervals, overdue ratios, historical spend.
- **Production Status**: Production-derivable, point-in-time safe, currently running in live inference.

### Tier O1 — Extended Observable (V2.2 EXTENDED60)
- **Feature Count**: 60
- **Origin**: V2.2 challenger baseline (`ridebase-ml/models/v2_2_v1_5/feature_list.json`)
- **Semantic Content**: Tier O0 + 6 legitimate appointment and breakdown signals:
  `prior_appointment_count`, `prior_no_show_count`, `prior_cancelled_appointment_count`, `known_appointment_within_30d`, `days_to_next_known_appointment`, `recent_breakdown_count_180d`.
- **Production Status**: Production-derivable, point-in-time safe.

### Tier O2 — Maximum Observable History (V2.3 — 95 Features)
- **Feature Count**: 95
- **Origin**: V2.3 behavior-state feature contract (`ridebase-ml/derived_outputs/v2_3_v1_5/v2_3_feature_dictionary.csv`)
- **Semantic Content**: Tier O1 + 35 granular point-in-time behavioral signals:
  Appointment conversion rate, cancellation rate, rebook rate, service delay dispersion (`interservice_days_cv`, `interservice_km_cv`), workshop loyalty streak, usage volatility, breakdown frequency.
- **Production Status**: Production-derivable, point-in-time safe.

---

### Tier L1 — Latent Stable Behavior Oracle (Generator Hidden Traits)
- **Variables**:
  - `oracle_latent_adherence`: Continuous adherence probability $[0.06, 0.96]$.
  - `oracle_latent_no_show_tendency`: Latent appointment failure propensity $[0.0, 1.0]$.
  - `oracle_latent_price_sensitivity`: Customer price elasticity propensity $[0.0, 1.0]$.
  - `oracle_latent_loyalty`: Workshop loyalty tendency $[0.0, 1.0]$.
  - `oracle_latent_churn_tendency`: Probability of abandoning RideBase network $[0.0, 1.0]$.
  - `oracle_latent_frailty`: Customer unobserved random effect / frailty $[0.52, 1.85]$.
  - `oracle_latent_profile`: Latent customer archetype (`NORMAL`, `ON_TIME`, `DELAYER`, `HEAVY_USER`, `PRICE_SENSITIVE`, `CHURN_RISK`, `WORKSHOP_LOYAL`, `NO_SHOW_PRONE`).
- **Timing & Availability**: Formed during customer creation / early history; available prior to future event simulation.
- **Leakage Review**: Zero future outcome leakage. Does not contain realization of future random draws.
- **Production Status**: **STRICTLY FORBIDDEN IN PRODUCTION**. Research audit only.

---

### Tier L2 — Landmark Latent Dynamic State Oracle
- **Variables**:
  - `oracle_latent_is_churned_at_landmark`: Binary flag (1 if customer has irrevocably churned as of landmark date, 0 otherwise).
  - `oracle_latent_step_hazard_periodic`: Generator periodic service hazard per 3-day simulation step at landmark date.
  - `oracle_latent_step_hazard_appointment_create`: Hazard of initiating an appointment at landmark date.
  - `oracle_latent_step_hazard_direct_periodic`: Hazard of walk-in periodic service at landmark date.
  - `oracle_latent_step_hazard_breakdown`: Breakdown hazard at landmark date.
  - `oracle_latent_step_hazard_repair`: Repair hazard at landmark date.
  - `oracle_latent_step_hazard_tire`: Tire wear service hazard at landmark date.
  - `oracle_latent_step_hazard_total`: Total combined step hazard ($\sum \lambda_{\text{service}}$) at landmark date.
- **Timing & Availability**: State known by the synthetic generator at landmark time $T$ before future events are drawn.
- **Leakage Review**: Zero future outcome leakage. Computed strictly from state $\le T$.
- **Production Status**: **STRICTLY FORBIDDEN IN PRODUCTION**. Research audit only.

---

### Tier H — True Generator Hazard / Propensity Oracle
- **Variables**:
  - `oracle_true_hazard_instantaneous`: Total instantaneous service arrival rate $\lambda(T)$ at landmark date.
  - `oracle_true_propensity_proxy`: Analytic cumulative hazard proxy $\Lambda_{30}(T) = 1 - \exp(-10 \cdot \lambda(T))$.
- **Semantic Meaning**: The theoretical Bayes-optimal ranking signal generated by the synthetic process itself at the landmark date.
- **Leakage Review**: Evaluated purely at time $T$. No future realization is used.
- **Production Status**: **STRICTLY FORBIDDEN IN PRODUCTION**. Research audit only.
