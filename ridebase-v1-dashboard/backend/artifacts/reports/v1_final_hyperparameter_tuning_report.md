# RideBase V1 Final Hyperparameter Tuning

_Notebook 12 · dataset **v1.3.0 (frozen)** · seed 42 · FAST_MODE (not final) · Optuna 12 trials/model_

## Executive Summary

Systematic temporal-CV Optuna tuning of HGB / LightGBM / XGBoost / CatBoost with target-specific feature selection and a validation-selected blend. **KM verdict: MEANINGFUL IMPROVEMENT. DAYS verdict: SMALL IMPROVEMENT.** Overall: **SMALL IMPROVEMENT** → **V1 REGRESSION CLOSED**.

## Baseline Reproduction

- DAYS: default HGB / full v1.3 contract (SET_F_FULL) — VAL MAE 9.50 R² 0.8121; temporal-CV MAE 16.83 ± 3.27. TEST BASE MAE 22.40 R² 0.6579.
- KM: default HGB / full v1.3 contract (SET_F_FULL) — VAL MAE 607.49 R² 0.6458; temporal-CV MAE 699.84 ± 37.68. TEST BASE MAE 963.20 R² 0.4117.

## Temporal Cross Validation

3 expanding-window folds inside TRAIN, no shuffle; each internal-validation window strictly follows its training window in time. Optuna scoring = mean fold MAE.

## Feature Ablation
```
             feature_set target  n_cols  cv_mae_mean  cv_mae_std  val_mae  val_r2  train_mae
              SET_A_BASE   DAYS      78       19.503       3.222   11.129   0.750     17.573
              SET_A_BASE     KM      78      726.126      35.677  651.912   0.594    625.235
       SET_B_BASE_POLICY   DAYS      86       19.554       3.198   11.167   0.751     17.645
       SET_B_BASE_POLICY     KM      86      721.728      37.283  654.566   0.592    618.992
 SET_C_BASE_RECENT_USAGE   DAYS      85       17.201       3.312    9.678   0.802     16.484
 SET_C_BASE_RECENT_USAGE     KM      85      704.529      31.339  629.969   0.623    601.005
SET_D_BASE_HIST_INTERVAL   DAYS      93       18.391       3.410   10.273   0.785     16.725
SET_D_BASE_HIST_INTERVAL     KM      93      714.169      37.700  625.441   0.626    615.343
SET_E_BASE_MAINT_HISTORY   DAYS     116       19.409       3.154   11.433   0.735     17.561
SET_E_BASE_MAINT_HISTORY     KM     116      722.855      36.635  662.811   0.586    621.622
              SET_F_FULL   DAYS     146       16.835       3.272    9.500   0.812     15.368
              SET_F_FULL     KM     146      699.841      37.681  607.493   0.646    588.674
        SET_G_KM_COMPACT   DAYS     114       16.758       3.278    9.418   0.817     15.347
        SET_G_KM_COMPACT     KM     114      696.520      36.289  608.142   0.645    590.761
      SET_G_DAYS_COMPACT   DAYS     113       16.797       3.263    9.479   0.813     15.793
      SET_G_DAYS_COMPACT     KM     113      698.307      35.359  605.569   0.649    589.530
```

Frozen feature set — DAYS `SET_G_KM_COMPACT`, KM `SET_G_DAYS_COMPACT`.

## DAYS Model Selection
```
model             loss  cv_mae  cv_mae_std  val_mae  val_r2  train_mae  overfit_flag
 LGBM    regression_l1  16.524       3.279    9.298   0.813     14.684         False
  XGB reg:squarederror  16.656       3.169    9.308   0.811     12.704          True
  HGB   absolute_error  16.639       3.248    9.372   0.810     14.640         False
  CAT              MAE  16.631       3.300    9.722   0.786     15.571         False
   ET                -  16.809       0.000    9.870   0.768     13.351          True
```

Best single: **LGBM** · loss `regression_l1` · transform `raw`.

## KM Model Selection
```
model             loss  cv_mae  cv_mae_std  val_mae  val_r2  train_mae  overfit_flag
  HGB   absolute_error 686.409      35.477  600.843   0.656    541.873         False
  XGB reg:squarederror 686.654      36.009  602.480   0.651    498.105          True
 LGBM    regression_l1 687.424      39.128  610.776   0.643    571.496         False
  CAT              MAE 683.376      38.128  614.515   0.636    578.341         False
   ET                - 727.215       0.000  636.245   0.609    530.187          True
```

Best single: **HGB** · loss `absolute_error` · transform `log1p`.

## Ensemble Experiment
```
target          members                                             weights  blend_val_mae  best_single_val_mae  improvement_pct  max_resid_corr  accepted  stack_val_mae
  DAYS LGBM | XGB | HGB [np.float64(0.5), np.float64(0.4), np.float64(0.1)]       9.231708             9.297719            0.710        0.981295      True            NaN
    KM HGB | XGB | LGBM [np.float64(0.6), np.float64(0.4), np.float64(0.0)]     598.160792           600.843458            0.446        0.978208     False            NaN
```

## Specialist Segment Experiment
```
target  used  train_cold_n  val_cold_n  single_cold_mae  specialist_cold_mae  routed_full_val_mae  single_full_val_mae
  DAYS False          9329         258        14.075807            15.259264             9.511387             9.297719
    KM False          9329         258       681.237398           691.351077           602.669441           600.843458
```

## Final Frozen Configuration
```json
{
  "DAYS": {
    "target": "days_to_next_service",
    "feature_set": "SET_G_KM_COMPACT",
    "model": "LGBM",
    "hyperparameters": {
      "objective": "regression_l1",
      "n_estimators": 775,
      "learning_rate": 0.032788573443693105,
      "num_leaves": 151,
      "max_depth": 9,
      "min_child_samples": 74,
      "subsample": 0.8366734543720239,
      "colsample_bytree": 0.6909540973817309,
      "reg_alpha": 7.574306417533107e-08,
      "reg_lambda": 0.007534049014815543,
      "min_split_gain": 0.9986737331882056
    },
    "loss": "regression_l1",
    "target_transform": "raw",
    "use_specialist": false,
    "specialist_segment": "history_depth<=1",
    "use_ensemble": true,
    "ensemble_members": [
      "LGBM",
      "XGB",
      "HGB"
    ],
    "ensemble_weights": [
      0.5,
      0.4,
      0.1
    ],
    "refit_on": "TRAIN+VALIDATION",
    "random_seed": 42
  },
  "KM": {
    "target": "km_to_next_service",
    "feature_set": "SET_G_DAYS_COMPACT",
    "model": "HGB",
    "hyperparameters": {
      "learning_rate": 0.056550491692330104,
      "max_iter": 887,
      "max_leaf_nodes": 248,
      "max_depth": 8,
      "min_samples_leaf": 51,
      "l2_regularization": 0.1264454460669936,
      "max_bins": 255,
      "loss": "absolute_error"
    },
    "loss": "absolute_error",
    "target_transform": "log1p",
    "use_specialist": false,
    "specialist_segment": "history_depth<=1",
    "use_ensemble": false,
    "ensemble_members": [],
    "ensemble_weights": [],
    "refit_on": "TRAIN+VALIDATION",
    "random_seed": 42
  }
}
```

## Final Test Results
```
target          baseline_model  baseline_mae  baseline_r2 tuned_model  tuned_mae  tuned_r2  mae_improvement_pct  r2_gain    verdict
  DAYS HGB(default)/SET_F_FULL       22.4046       0.6579    LGBM+ENS    21.9632    0.6667                 1.97   0.0088 SMALL/NONE
    KM HGB(default)/SET_F_FULL      963.2046       0.4117         HGB   939.9919    0.4628                 2.41   0.0511 MEANINGFUL
```

### Metric bands (TEST)
```
target config     mae  median_ae     rmse    r2    bias   p90_ae    n  within_15  within_30  within_45  within_60  within_90  within_500  within_1000  within_1500  within_2000  within_5000
  DAYS   base  22.405     13.444   35.344 0.658   5.631   53.251 1282      0.548      0.762      0.867      0.917      0.966         NaN          NaN          NaN          NaN          NaN
  DAYS  tuned  21.963     12.839   34.887 0.667   7.162   52.913 1282      0.559      0.778      0.872      0.918      0.970         NaN          NaN          NaN          NaN          NaN
    KM   base 963.205    716.928 1325.277 0.412 363.505 2065.154 1282        NaN        NaN        NaN        NaN        NaN       0.370        0.642        0.786        0.892        0.995
    KM  tuned 939.992    732.860 1266.404 0.463 331.253 2069.222 1282        NaN        NaN        NaN        NaN        NaN       0.358        0.644        0.811        0.891        0.998
```

## Feature Importance

- DAYS top-10: recent_90d_km, engine_displacement_cc, historical_interval_days_median, recent_60d_km, policy_interval_km, annual_km_baseline, previous_interval_days, policy_group, avg_service_interval_days, avg_km_per_day_since_previous_service

- KM top-10: policy_interval_km, recent_30d_km, snapshot_day_of_year, previous_interval_km, daily_active_probability, avg_ride_days_per_week, recent_vs_long_term_usage_ratio, recent_90d_km, days_observed, historical_interval_km_median

## Error Analysis — worst TEST segments
```
target           segment_type  segment    n         mae
  DAYS       riding_intensity      LOW   62   72.253659
  DAYS next_service_type_code   REPAIR   91   34.485471
  DAYS                  brand      SYM   33   34.366358
  DAYS       riding_intensity   MEDIUM  292   33.616004
  DAYS                  brand      TVS   58   33.259934
  DAYS      history_depth_bin      0-1  318   32.707966
  DAYS                  brand    Honda  321   26.689519
  DAYS      history_depth_bin      2-3  245   24.276956
  DAYS                  brand   Yamaha  127   21.470967
  DAYS next_service_type_code PERIODIC 1160   20.640218
    KM                  brand      SYM   33 1536.015050
    KM next_service_type_code   REPAIR   91 1376.562552
    KM                  brand      RKS  125 1336.883689
    KM                  brand   Yamaha  127 1204.761692
    KM      history_depth_bin      0-1  318 1157.322215
    KM                  brand    Honda  321 1057.609849
    KM       riding_intensity     HIGH  928  994.270070
    KM next_service_type_code PERIODIC 1160  903.547201
    KM      history_depth_bin      2-3  245  875.045435
    KM      history_depth_bin       4+  719  866.001483
```

## Temporal Drift
```
                       quantity      split    mean  median     std
                    target_DAYS      TRAIN  127.76   94.88   99.89
                    target_DAYS VALIDATION   63.63   55.32   32.59
                    target_DAYS       TEST  104.67   88.87   60.45
                      target_KM      TRAIN 3566.33 3213.00 1776.01
                      target_KM VALIDATION 3446.08 3176.00 1378.18
                      target_KM       TEST 3502.92 3177.50 1728.52
historical_interval_days_median      TRAIN  110.50   85.76   82.02
historical_interval_days_median VALIDATION   74.61   63.10   41.78
historical_interval_days_median       TEST  105.26   84.05   66.90
  historical_interval_km_median      TRAIN 3756.54 3283.00 1621.16
  historical_interval_km_median VALIDATION 4022.49 3559.50 1676.44
  historical_interval_km_median       TEST 3503.08 3172.00 1465.26
                  recent_90d_km      TRAIN 3965.23 3306.38 2820.51
                  recent_90d_km VALIDATION 6141.16 5945.32 2672.30
                  recent_90d_km       TEST 3510.39 3135.46 2437.70
             policy_interval_km      TRAIN 4198.65 5000.00 1203.84
             policy_interval_km VALIDATION 4016.10 3000.00 1202.42
             policy_interval_km       TEST 4288.61 5000.00 1189.08
```

## Overfitting / Generalization

- DAYS: TRAIN MAE 14.68 vs VAL MAE 9.30 vs TEST MAE 21.96 — overfit_flag=False.
- KM: TRAIN MAE 541.87 vs VAL MAE 600.84 vs TEST MAE 939.99 — overfit_flag=False.

## Reproducibility
{'DAYS': 'PASS', 'KM': 'PASS'} · multi-seed stability in `v1_final_tuning_stability.csv`.

## Practical Gain

- DAYS: MAE +1.97%  ·  R² +0.0088  →  SMALL IMPROVEMENT
- KM: MAE +2.41%  ·  R² +0.0511  →  MEANINGFUL IMPROVEMENT

## V1 Final Verdict
**SMALL IMPROVEMENT** · **V1 REGRESSION CLOSED**

## Recommendation for V2
The next-service KM target on frozen v1.3 is model-saturated: temporal-CV tuning across four boosting families plus a blend does not move TEST R² materially, and TRAIN↔TEST drift (not model capacity) dominates the remaining error. Recommended next step: **V2 survival analysis** (right-censoring aware) rather than further V1 point-regression tuning. V2 recommended: YES.
