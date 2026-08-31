# V1 External Maintenance Knowledge — Report

## Executive Summary
Real manufacturer maintenance-schedule features from `ridebase-ml/external_knowledge/`
(23 policies, 432 task rows, 24 official source docs; 19 resolved /
4 partial / 16 unresolved models) were converted into leakage-safe derived
features and A/B tested against the frozen RideBase v1.3 next-service regression, same split, same
default `HistGradientBoostingRegressor(random_state=42)`.

Knowledge covers **54.9% of observed TEST rows**
(exact-match 43.7%).

**KM TEST — FULL:** BASE R² 0.4343 / MAE 937.3  →  KNOWLEDGE R² 0.4340 / MAE 944.6
(ΔR² -0.0003, ΔMAE -7.4).
**KM TEST — COVERED:** BASE R² 0.5102 / MAE 895.0  →  KNOWLEDGE R² 0.5022 / MAE 917.5
(ΔR² -0.0080, ΔMAE -22.5).

**Verdict: NO VALUE.**  Suitable for V1 KM: NO · V1 DAYS: NO · V3 next-task: YES.

## Research Question
Does real manufacturer maintenance-schedule knowledge, added to the v1.3 leakage-free snapshot
features, meaningfully improve next-service KM prediction (secondary: DAYS)?

## V1.3 Baseline
BASE (146 leakage-safe features, default HGB): DAYS TEST R² 0.6946 MAE 21.26 ·
KM TEST R² 0.4343 MAE 937.3.

## External Knowledge Base
23 policy rows, 432 task rows (HIGH 336 / MEDIUM 86 / LOW 10),
24 source documents, 2 source conflicts. Primary experiment uses HIGH+MEDIUM only.

## Model Coverage
Resolved 19, partial 4, unresolved 16 of 39.
Bridged to RideBase model_id for 23 models.

## Row-Level Coverage
     split  observed_rows  knowledge_rows  knowledge_row_pct  exact_match_rows  exact_match_row_pct
     TRAIN          25442           14426             0.5670             11777               0.4629
VALIDATION           1429             717             0.5017               549               0.3842
      TEST           1282             704             0.5491               560               0.4368

## Mapping Quality
match_type ∈ {NORMALIZED_EXACT, VARIANT_MATCH, GENERATION_MISMATCH}; UNRESOLVED never used.
Match-quality flags: market_match_exact, year_match_exact, variant_match_exact, mapping_confidence_score.

## Confidence Filtering
confidence_filter  km_val_mae  km_val_r2  days_val_mae  days_val_r2
        HIGH_only    610.2475     0.6444        9.5689       0.8095
      HIGH_MEDIUM    614.4948     0.6397        9.6528       0.8035
  HIGH_MEDIUM_LOW    610.4777     0.6419        9.6853       0.8005
Primary = HIGH+MEDIUM (frozen on VALIDATION, not TEST).

## Manufacturer Policy Features
service_interval_km/months, first_service_km, service_rule_type, km_to_next_manufacturer_service,
km_since_previous_grid, service_stage/grid_index, overdue_km, due_now_flag, months/days_to_next,
due_pressure = min(normalised km-remaining, normalised time-remaining).

## Task-Level Due Features
km_to_next_<TASK> for 13 canonical tasks (action-aware: air-filter replace vs clean,
spark-plug replace vs inspect), tasks_due_next_{250,500,1000,2000,5000}km, safety/replace/inspect
due counts, km_to_next_major_maintenance (explicit rule: next due REPLACE among valve/coolant/brake-fluid/final-drive).
Non-covered models → NULL (never 0).

## Leakage Audit
All 54 knowledge features derived from snapshot_odometer_km + motorcycle_age_years +
static manufacturer schedule constants. uses_actual_next_service = NO for every feature. Status: PASS.

## Feature Ablation
                 feature_set    rows  km_val_mae  km_val_r2  days_val_mae  days_val_r2  knowledge_coverage_in_rows
                  SET_A_BASE     ALL    612.7795     0.6427        9.4207       0.8174                       0.567
           SET_B_BASE_POLICY     ALL    609.1699     0.6447        9.5043       0.8103                       0.567
      SET_C_BASE_POLICY_TASK     ALL    612.6567     0.6414        9.5367       0.8105                       0.567
SET_D_BASE_POLICY_TASK_MATCH     ALL    614.4948     0.6397        9.6528       0.8035                       0.567
          SET_E_COVERED_ONLY COVERED    642.1342     0.6606       10.2223       0.7847                       1.000
             SET_F_HIGH_ONLY     ALL    610.2475     0.6444        9.5689       0.8095                       0.567
           SET_G_HIGH_MEDIUM     ALL    614.4948     0.6397        9.6528       0.8035                       0.567

## HGB Same-Model A/B Test
BASE vs SET_D (BASE + policy + task + match/confidence), identical HGB. See feature ablation + validation
metrics tables.

## Covered-Model Analysis
COVERED = TEST observed rows with manufacturer_knowledge_available == 1
(704 rows, 54.9% of TEST).
EXACT = covered + variant-exact + confidence ≥ MEDIUM (560 rows).

## Secondary Model Check
 family  base_km_val_mae  knowledge_km_val_mae  km_val_mae_gain  base_km_val_r2  knowledge_km_val_r2  km_val_r2_gain
XGBoost         630.5121              613.4700          17.0421          0.6241               0.6426          0.0185
    HGB         612.7795              614.4948          -1.7153          0.6427               0.6397         -0.0029
Family-consistent contribution: False.

## Final Test (opened once)
 subset target    config     mae  median_ae     rmse     r2    bias   p90_ae    n  within_15  within_30  within_60  within_500  within_1000  within_1500  within_2000
   FULL     KM      BASE 937.257    669.167 1299.605  0.434 328.986 2077.723 1282        NaN        NaN        NaN       0.399        0.642        0.802        0.890
   FULL     KM KNOWLEDGE 944.644    680.776 1299.906  0.434 350.932 2112.962 1282        NaN        NaN        NaN       0.379        0.647        0.800        0.892
   FULL     KM      GAIN  -7.387    -11.609   -0.301 -0.000 350.932  -35.238 1282        NaN        NaN        NaN         NaN          NaN          NaN          NaN
COVERED     KM      BASE 895.017    622.730 1281.981  0.510 226.644 2007.850  704        NaN        NaN        NaN       0.426        0.666        0.822        0.899
COVERED     KM KNOWLEDGE 917.494    630.468 1292.426  0.502 268.727 2000.192  704        NaN        NaN        NaN       0.388        0.665        0.812        0.899
COVERED     KM      GAIN -22.478     -7.738  -10.445 -0.008 268.727    7.657  704        NaN        NaN        NaN         NaN          NaN          NaN          NaN
  EXACT     KM      BASE 833.991    576.872 1204.410  0.451 202.281 1813.900  560        NaN        NaN        NaN       0.448        0.691        0.850        0.920
  EXACT     KM KNOWLEDGE 854.576    586.670 1219.482  0.437 232.787 1807.592  560        NaN        NaN        NaN       0.414        0.693        0.836        0.921
  EXACT     KM      GAIN -20.585     -9.799  -15.072 -0.014 232.787    6.307  560        NaN        NaN        NaN         NaN          NaN          NaN          NaN

DAYS:
 subset target    config    mae  median_ae   rmse     r2  bias  p90_ae    n  within_15  within_30  within_60  within_500  within_1000  within_1500  within_2000
   FULL   DAYS      BASE 21.264     12.636 33.395  0.695 6.599  49.278 1282      0.559      0.776      0.931         NaN          NaN          NaN          NaN
   FULL   DAYS KNOWLEDGE 22.498     13.122 35.278  0.659 9.223  53.967 1282      0.544      0.764      0.919         NaN          NaN          NaN          NaN
   FULL   DAYS      GAIN -1.233     -0.486 -1.882 -0.035 9.223  -4.689 1282        NaN        NaN        NaN         NaN          NaN          NaN          NaN
COVERED   DAYS      BASE 22.845     13.356 36.123  0.665 6.931  51.503  704      0.538      0.751      0.925         NaN          NaN          NaN          NaN
COVERED   DAYS KNOWLEDGE 24.227     14.016 38.076  0.627 9.746  58.314  704      0.526      0.733      0.908         NaN          NaN          NaN          NaN
COVERED   DAYS      GAIN -1.382     -0.660 -1.953 -0.037 9.746  -6.811  704        NaN        NaN        NaN         NaN          NaN          NaN          NaN
  EXACT   DAYS      BASE 22.765     12.846 36.099  0.687 7.065  52.209  560      0.541      0.750      0.925         NaN          NaN          NaN          NaN
  EXACT   DAYS KNOWLEDGE 24.124     13.640 38.020  0.653 9.664  58.734  560      0.523      0.734      0.907         NaN          NaN          NaN          NaN
  EXACT   DAYS      GAIN -1.360     -0.794 -1.921 -0.034 9.664  -6.525  560        NaN        NaN        NaN         NaN          NaN          NaN          NaN

## Feature Importance
Top-10 (permutation, KM VAL MAE): policy_interval_km, recent_30d_km, snapshot_day_of_year, previous_interval_km, daily_active_probability, recent_vs_long_term_usage_ratio, avg_ride_days_per_week, days_observed, historical_interval_km_median, recent_90d_km.
Manufacturer features in top-30: 3. Group importance %: {'BASE_FEATURES': 99.94, 'POLICY_KNOWLEDGE': -0.07, 'TASK_DUE_KNOWLEDGE': 0.09, 'MATCH_QUALITY': 0.04}.

## Error Analysis
Schedule vs actual (covered observed): Spearman 0.2645, Pearson 0.2693.
Policy gap (actual − schedule) median 1581.0 km, |gap| median 1796.0 km.
Error by event type:
event_type    n  base_km_mae  knowledge_km_mae  delta
  PERIODIC 1304        580.5             579.2    1.4
    REPAIR   91        967.4            1011.5  -44.1
 BREAKDOWN   18       1025.3            1049.7  -24.4
      TIRE   16        759.0             745.7   13.4

## Knowledge Coverage Limitations
23/39 models carry a schedule; Honda, Kuba, RKS, CFMOTO are the coverage gaps
(677 TEST rows, 52.8% of TEST). Global gain is diluted by these
uncovered rows; read FULL and COVERED together.

## Value for V1 KM
NO. FULL ΔR² -0.0003 / ΔMAE -7.4; COVERED ΔR² -0.0080 / ΔMAE -22.5.

## Value for V1 DAYS
NO. FULL ΔMAE -1.23.

## Value for V3 Next-Task
YES. Task rows expose canonical_task_code + action + repeat_every_km/months = direct weak prior
for "which task is due next".

## Production Implications
All knowledge features are PRODUCTION_DERIVABLE (manufacturer schedule + odometer/age; no synthetic latent).
The knowledge layer is safe to fold into a production feature store keyed by model_id.

## Final Verdict
NO VALUE. Result reported as measured; no knowledge file, target, or split was altered to chase the score.
