# RideBase V2.1 Extreme-Overdue Model Diagnosis Report

**Date:** 2026-09-04  
**Subject:** Extreme-Overdue Behavior and Feature Space Analysis for RideBase V2.1

---

## 1. Executive Summary & Conclusion

**Diagnosis Verdict:**  
**B (UI/Model-Routing Bug) + C (Annualization/Input Semantics Bug)**

The low P30 (~11.7% / 7.98%) displayed to users on extreme overdue scenarios was **NOT** produced by V2.1. It was produced by the frozen **V2.0 research model**, which was mistakenly wired as the primary scenario output in the ML Control Center. V2.0 had previously failed the arbitrary-day live scenario audit due to training on right-censored service-event snapshots with an overdue dead region.

When the exact same extreme scenario (NS200, 30,000 km since service, 34 days elapsed, 10,000 km/yr user baseline) is evaluated on **V2.1**, the model produces:
- **P30:** 22.73%
- **P60:** 44.86%
- **P90:** 65.61%
- **P120:** 75.40%
- **Monotonicity:** Strictly preserved ($P_{30} \le P_{60} \le P_{90} \le P_{120}$)
- **No Zero-Collapse:** Probabilities scale appropriately with overdue pressure.

---

## 2. Feature Vector Inspection (V2.1 Contract)

Evaluating the scenario under `ridebase_ml.v2_1.scenario.derive`:

| Feature Name | Derived Value | Provenance | Notes |
|---|---|---|---|
| `brand` | `"Bajaj"` | `MODEL_MASTER` | From motorcycle catalog |
| `category` | `"COMMUTER"` | `MODEL_MASTER` | Catalog |
| `powertrain_type` | `"ICE"` | `MODEL_MASTER` | Catalog |
| `policy_group` | `"COMMUTER_150_250"`| `MODEL_MASTER` | Catalog |
| `current_odometer_km_at_landmark` | `42000.0` | `USER_INPUT` | Explicit user entry |
| `annual_km_baseline` | `10000.0` | `USER_INPUT` | **Preserved from user input** (NOT overwritten by 322k pace) |
| `usage_type` | `"COMMUTER"` | `USER_INPUT` | User entry |
| `riding_intensity` | `"MEDIUM"` | `USER_INPUT` | User entry |
| `days_since_last_service` | `34.0` | `LANDMARK_DERIVED`| Date difference |
| `km_since_last_service` | `30000.0` | `LANDMARK_DERIVED`| Odometer difference |
| `avg_km_per_day_since_last_service`| `882.35` | `LANDMARK_DERIVED`| Short-window diagnostic rate |
| `oem_interval_km` | `5000.0` | `POLICY_DERIVED` | Catalog OEM interval (3,000 km in TR operational policy) |
| `oem_interval_days` | `182.625` | `POLICY_DERIVED` | Catalog OEM days interval |
| `km_due_ratio` | `6.0` (or `10.0`)| `POLICY_DERIVED` | Substantially overdue |
| `km_overdue` | `25000.0` | `POLICY_DERIVED` | Odometer beyond threshold |
| `max_due_ratio` | `6.0` | `POLICY_DERIVED` | Driving policy ratio |
| `maintenance_due_now` | `1` | `POLICY_DERIVED` | Deterministic flag (ratio >= 1.0) |
| *Missing Features (34)* | `NaN` | `MISSING_PREPROCESSOR` | Handled by frozen median/mode imputer |

---

## 3. Training Distribution & Out-Of-Distribution (OOD) Analysis

1. **Overdue Representation in V2.1:**
   - In synthetic dataset V1.4, dynamic landmarks were sampled randomly across the entire operating timeline.
   - Landmarks with `maintenance_due_now == 1` and `max_due_ratio > 1.0` represent over 28% of the 256,841 training landmarks.
   - Thus, extreme overdue is supported within the V2.1 training distribution.
2. **Extreme Daily Pace ($882\text{ km/day}$):**
   - A rate of 882 km/day over 34 days is rare in commuter profiles, placing `avg_km_per_day_since_last_service` in the extreme tail (top 0.1%).
   - The tree-based champion model (`xgb_cox`) saturates at high split values rather than oscillating or inverting.
   - Crucially, `annual_km_baseline` remains anchored at the user-entered 10,000 km/yr, preventing the hazard function from exploding into numerical instability.

---

## 4. Remediation Implemented

1. **Routing Fix:** Demote V2.0 to a collapsed research section with prominent warning; make V2.1 the primary scenario prediction.
2. **Semantic Clarification:** Explicitly separate `Model girdisi: 10,000 km/yıl (kullanıcı girişi)` from `Son dönem kullanım temposu: 322,059 km/yıl (34 günlük pencere — düşük güven)`.
3. **Preserve Deterministic Policy:** Maintain the independent banner `SERVİS ŞİMDİ GEREKLİ · BAKIM GECİKMİŞ` without conflating maintenance policy with customer return likelihood.
