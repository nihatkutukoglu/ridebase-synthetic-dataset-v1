# RideBase 10 — V1.3 Final Regression

## Executive Summary

RideBase Synthetic Dataset **v1.3** (regression-calibration, FROZEN) üzerinde model-engineering
deneyi. DAYS final: **best_single**, KM final: **best_single**.
V1.3 Basic HGB → V1.3 Final TEST R² değişimi: DAYS +0.0134 (0.6471→0.6605),
KM -0.0344 (0.4250→0.3906). Ortalama MAE iyileşmesi -1.99%.
Regression ceiling: **V1.3 REGRESSION CEILING REACHED**. Production validation **BLOCKED**.

## Dataset Guard
dataset_version=1.3.0, generator_version=1.3.0,
regression_calibration_experiment=true. Split {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470}. Observed {'TRAIN': 25442, 'VALIDATION': 1429, 'TEST': 1282}.

## V1.3 Regression Calibration Context
This release is a synthetic generator calibration experiment intended to test the learnability of next-service timing/mileage from snapshot-available features. It is not production validation.
Noise calibration: {'main_regular_log_scale': 0.14, 'main_irregular_log_scale': 0.19, 'bounded_factor': [0.67, 1.43], 'selection_reason': 'reasonable realism, not score maximizing', 'sensitivity_table': 'reports/tables/regression_noise_sensitivity.csv'}

## Target & Censoring Contract
NEXT ANY SERVICE, RAW days / RAW km-delta. Yalnız observed target (n TRAIN 25442,
VAL 1429, TEST 1282). Censored snapshot regression target değil;
0/-1/median doldurma yok. Target/noise/split DEĞİŞTİRİLMEDİ.

## Feature Inventory
Toplam feature 146 (numeric 122, categorical 24).
Grup boyutları: { BASE:78, POLICY:8, RECENT_USAGE:7, HISTORICAL_INTERVAL:15, MAINTENANCE_HISTORY:38 }.
Synthetic-only dışlanan: ['behavior_label', 'noise_z', 'deterministic_days', 'deterministic_km', 'failure_hazard_score', 'chronic_risk_tier'].

## Leakage Audit
USED feature'ların hiçbiri future/target-derived, identifier veya synthetic-only değil →
`v1_3_final_feature_leakage_audit.csv`.

## Baseline Reproduction
| target   |     r2 |      mae |   median_ae |   p90_ae |
|:---------|-------:|---------:|------------:|---------:|
| DAYS     | 0.6471 |  22.6242 |      12.936 |    54.38 |
| KM       | 0.425  | 948.186  |     699.072 |  2108.03 |
Rapor değerleri DAYS R²≈0.6398 / MAE≈22.78, KM R²≈0.4134 / MAE≈969. Flag: {'DAYS': 'OK', 'KM': 'OK'}.

## Feature Ablation
| feature_set               |   feature_count |   days_val_mae |   days_val_r2 |   km_val_mae |   km_val_r2 |   incremental_gain | notes                             |
|:--------------------------|----------------:|---------------:|--------------:|-------------:|------------:|-------------------:|:----------------------------------|
| SET_A_BASE                |             177 |        11.2414 |        0.7436 |      650.856 |      0.5961 |             0      | same default HGB, full VALIDATION |
| SET_B_POLICY              |             204 |        11.1744 |        0.7508 |      658.266 |      0.5919 |             0.067  | same default HGB, full VALIDATION |
| SET_C_RECENT_USAGE        |             211 |         9.617  |        0.8054 |      627.099 |      0.6214 |             1.5574 | same default HGB, full VALIDATION |
| SET_D_HISTORICAL_INTERVAL |             239 |         9.7195 |        0.7972 |      607.358 |      0.6475 |            -0.1025 | same default HGB, full VALIDATION |
| SET_E_MAINT_HISTORY       |             281 |         9.6746 |        0.8011 |      612.344 |      0.6435 |             0.0449 | same default HGB, full VALIDATION |
| SET_F_FULL                |             281 |         9.6746 |        0.8011 |      612.344 |      0.6435 |             0      | same default HGB, full VALIDATION |
En iyi set: DAYS=SET_C_RECENT_USAGE, KM=SET_D_HISTORICAL_INTERVAL.

## Encoded vs Native Categorical
`v1_3_model_validation_results.csv` — her modelin representation'ı ve validation MAE/R²'si.

## Model Validation (single models)
| target   | model                              | representation   |   val_mae |   val_r2 |   val_median_ae |
|:---------|:-----------------------------------|:-----------------|----------:|---------:|----------------:|
| DAYS     | AutoGluon_best                     | autogluon        |    7.3121 |   0.8962 |          4.959  |
| DAYS     | XGBRegressor                       | encoded          |    9.1013 |   0.8272 |          6.1073 |
| DAYS     | LGBMRegressor                      | native           |    9.2236 |   0.8219 |          6.1775 |
| DAYS     | HistGradientBoostingRegressor      | encoded          |    9.2765 |   0.8242 |          6.2742 |
| DAYS     | CatBoostRegressor                  | native           |    9.4848 |   0.7844 |          5.9802 |
| DAYS     | GradientBoosting_Huber(diagnostic) | encoded          |    9.7091 |   0.7961 |          6.4031 |
| DAYS     | ExtraTreesRegressor                | encoded          |    9.8391 |   0.7667 |          6.0764 |
| DAYS     | RandomForestRegressor              | encoded          |   10.0755 |   0.7585 |          6.3711 |
| KM       | AutoGluon_best                     | autogluon        |  465.46   |   0.8011 |        365.531  |
| KM       | LGBMRegressor                      | native           |  599.89   |   0.6552 |        471.632  |
| KM       | HistGradientBoostingRegressor      | encoded          |  605.067  |   0.6462 |        459.022  |
| KM       | XGBRegressor                       | encoded          |  606.296  |   0.6474 |        476.76   |
| KM       | CatBoostRegressor                  | native           |  614.88   |   0.6328 |        473.112  |
| KM       | RandomForestRegressor              | encoded          |  620.345  |   0.6268 |        488.269  |
| KM       | ExtraTreesRegressor                | encoded          |  634.797  |   0.6091 |        488.536  |
| KM       | GradientBoosting_Huber(diagnostic) | encoded          |  642.14   |   0.613  |        510.932  |

## AutoGluon
| target   |   budget_s |   val_mae |   val_median_ae |   val_rmse |   val_r2 |   val_bias |   val_p90_ae |   val_within_15 |   val_within_30 |   val_within_45 |   val_within_60 |   val_within_90 |   val_within_500 |   val_within_1000 |   val_within_1500 |   val_within_2000 |   val_within_5000 |
|:---------|-----------:|----------:|----------------:|-----------:|---------:|-----------:|-------------:|----------------:|----------------:|----------------:|----------------:|----------------:|-----------------:|------------------:|------------------:|------------------:|------------------:|
| DAYS     |        900 |    7.3121 |           4.959 |    10.4979 |   0.8962 |     0.4983 |      16.5998 |          0.8768 |          0.9818 |          0.9965 |          0.9993 |               1 |         nan      |          nan      |          nan      |           nan     |               nan |
| KM       |        900 |  465.46   |         365.531 |   614.395  |   0.8011 |     8.8475 |     998.462  |        nan      |        nan      |        nan      |        nan      |             nan |           0.6368 |            0.9006 |            0.9748 |             0.993 |                 1 |

## Model Diversity
DAYS/KM validation-prediction korelasyon matrisleri kaydedildi
(`v1_3_prediction_correlation_*.csv`, figür 15).

## Ensemble
| target   | ensemble                     | members                                                                       | weights                                                                                                  |   val_mae |   val_r2 |
|:---------|:-----------------------------|:------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------|----------:|---------:|
| DAYS     | best_single                  | AutoGluon_best                                                                | -                                                                                                        |    7.3121 |   0.8962 |
| DAYS     | simple_average               | AutoGluon_best | XGBRegressor | LGBMRegressor | HistGradientBoostingRegressor | equal                                                                                                    |    8.6248 |   0.848  |
| DAYS     | weighted_mae_blend           | AutoGluon_best | XGBRegressor | LGBMRegressor | HistGradientBoostingRegressor | {"AutoGluon_best": 1.0, "XGBRegressor": 0.0, "LGBMRegressor": 0.0, "HistGradientBoostingRegressor": 0.0} |    7.3121 |   0.8962 |
| DAYS     | r2_focused_blend(diagnostic) | AutoGluon_best | XGBRegressor | LGBMRegressor | HistGradientBoostingRegressor | {"AutoGluon_best": 1.0, "XGBRegressor": 0.0, "LGBMRegressor": 0.0, "HistGradientBoostingRegressor": 0.0} |    7.3121 |   0.8962 |
| KM       | best_single                  | AutoGluon_best                                                                | -                                                                                                        |  465.46   |   0.8011 |
| KM       | simple_average               | AutoGluon_best | LGBMRegressor | HistGradientBoostingRegressor | XGBRegressor | equal                                                                                                    |  562.358  |   0.6985 |
| KM       | weighted_mae_blend           | AutoGluon_best | LGBMRegressor | HistGradientBoostingRegressor | XGBRegressor | {"AutoGluon_best": 1.0, "LGBMRegressor": 0.0, "HistGradientBoostingRegressor": 0.0, "XGBRegressor": 0.0} |  465.46   |   0.8011 |
| KM       | r2_focused_blend(diagnostic) | AutoGluon_best | LGBMRegressor | HistGradientBoostingRegressor | XGBRegressor | {"AutoGluon_best": 1.0, "LGBMRegressor": 0.0, "HistGradientBoostingRegressor": 0.0, "XGBRegressor": 0.0} |  465.46   |   0.8011 |
Final seçim (VALIDATION MAE): DAYS=best_single, KM=best_single.
Ensemble tek modeli anlamlı geçmediyse tek model korunur.

## Final Test
| metric                    |     DAYS |        KM |
|:--------------------------|---------:|----------:|
| bias                      |   4.0234 |  479.784  |
| mae                       |  22.2104 | 1003.25   |
| median_ae                 |  12.8745 |  762.702  |
| negative_prediction_count |   0      |    0      |
| p90_ae                    |  54.2781 | 2150.13   |
| r2                        |   0.6605 |    0.3906 |
| rmse                      |  35.2087 | 1348.84   |
| within_1000               | nan      |    0.6092 |
| within_15                 |   0.5515 |  nan      |
| within_1500               | nan      |    0.7746 |
| within_2000               | nan      |    0.8814 |
| within_30                 |   0.7668 |  nan      |
| within_45                 |   0.8541 |  nan      |
| within_500                | nan      |    0.3448 |
| within_5000               | nan      |    0.9969 |
| within_60                 |   0.9228 |  nan      |
| within_90                 |   0.9696 |  nan      |

## V1.2 vs V1.3 Comparison
| target   | model                 |       mae |   median_ae |     r2 |   within_30 |   within_60 |   within_1000 |   within_2000 |
|:---------|:----------------------|----------:|------------:|-------:|------------:|------------:|--------------:|--------------:|
| DAYS     | V1.2 Basic            |   23.0416 |     17.7582 | 0.4172 |      0.7639 |      0.9378 |      nan      |      nan      |
| DAYS     | V1.2 Advanced         |   22.2058 |     16.5551 | 0.4349 |      0.7834 |      0.942  |      nan      |      nan      |
| DAYS     | V1.2 AutoML           |   20.8053 |     14.157  | 0.4379 |      0.8013 |      0.9336 |      nan      |      nan      |
| DAYS     | V1.3 Basic HGB        |   22.6242 |     12.936  | 0.6471 |      0.7683 |      0.9181 |      nan      |      nan      |
| DAYS     | V1.3 Final Regression |   22.2104 |     12.8745 | 0.6605 |      0.7668 |      0.9228 |      nan      |      nan      |
| KM       | V1.2 Basic            | 1520.15   |   1069.47   | 0.2355 |    nan      |    nan      |        0.4718 |        0.7647 |
| KM       | V1.2 Advanced         | 1510.18   |   1091.47   | 0.2481 |    nan      |    nan      |        0.4638 |        0.7536 |
| KM       | V1.2 AutoML           | 1402.56   |    656.804  | 0.1386 |    nan      |    nan      |        0.6175 |        0.7742 |
| KM       | V1.3 Basic HGB        |  948.186  |    699.072  | 0.425  |    nan      |    nan      |        0.6396 |        0.883  |
| KM       | V1.3 Final Regression | 1003.25   |    762.702  | 0.3906 |    nan      |    nan      |        0.6092 |        0.8814 |

## Feature Importance (top)
| target   |   rank | feature                              |   importance |
|:---------|-------:|:-------------------------------------|-------------:|
| DAYS     |      1 | num__engine_displacement_cc          |       4.7139 |
| DAYS     |      2 | num__historical_interval_days_median |       3.9272 |
| DAYS     |      3 | num__recent_90d_km                   |       3.3368 |
| DAYS     |      4 | num__recent_60d_km                   |       1.7619 |
| DAYS     |      5 | num__previous_interval_days          |       1.2121 |
| DAYS     |      6 | num__annual_km_baseline              |       1.0161 |
| DAYS     |      7 | num__policy_interval_km              |       0.3548 |
| DAYS     |      8 | num__avg_km_per_active_day           |       0.0922 |
| KM       |      1 | policy_group                         |     251.926  |
| KM       |      2 | recent_30d_km                        |     141.316  |
| KM       |      3 | snapshot_day_of_year                 |      66.1617 |
| KM       |      4 | previous_interval_km                 |      25.3652 |
| KM       |      5 | recent_vs_long_term_usage_ratio      |      22.7793 |
| KM       |      6 | avg_ride_days_per_week               |      19.2261 |
| KM       |      7 | recent_90d_km                        |      18.0167 |
| KM       |      8 | daily_active_probability             |      14.1573 |

Signal-group katkısı: `v1_3_signal_validation.csv`.
| target   | feature_group       |   features_in_top20 |   importance_sum |
|:---------|:--------------------|--------------------:|-----------------:|
| DAYS     | BASE                |                   5 |           5.8442 |
| DAYS     | HISTORICAL_INTERVAL |                   7 |           5.3632 |
| DAYS     | RECENT_USAGE        |                   5 |           5.2055 |
| DAYS     | POLICY              |                   3 |           0.4112 |
| KM       | POLICY              |                   1 |         251.926  |
| KM       | RECENT_USAGE        |                   3 |         182.112  |
| KM       | BASE                |                  10 |         143.411  |
| KM       | HISTORICAL_INTERVAL |                   6 |          47.9678 |

## Error Analysis
En yüksek yeterli-örnekli DAYS segment MAE: riding_intensity=LOW
(n=62, MAE=69.22).
KM: history_depth=1 (n=161, MAE=1418.4).

## Distribution Drift
| target   |   train_mean |   val_mean |   test_mean | drift   |
|:---------|-------------:|-----------:|------------:|:--------|
| DAYS     |       127.76 |      63.63 |      104.67 | HIGH    |
| KM       |      3566.33 |    3446.08 |     3502.92 | LOW     |
DAYS split ortalamaları arasında büyük fark (drift HIGH); KM stabil. Hedef-quintile ve
snapshot-ay bazlı hata `v1_3_error_segments.csv` / figür 13-14'te.

## Observed / Censored Shift
Durum: **MATERIAL** (max |SMD| = 0.968,
historical_interval_days_median). Censored target üretilmedi; V1 observed-only selection bias sürüyor.

## Reproducibility
| target   |   max_abs_diff | status   |
|:---------|---------------:|:---------|
| DAYS     |              0 | PASS     |
| KM       |              0 | PASS     | (random_seed=42, final pipeline iki kez fit).

## Overfit Check
| target   |   train_mae |   val_mae |   test_mae |   train_r2 |   val_r2 |   test_r2 | overfit_warning   |
|:---------|------------:|----------:|-----------:|-----------:|---------:|----------:|:------------------|
| DAYS     |     13.6635 |    7.3121 |    22.2104 |     0.9558 |   0.8962 |    0.6605 | NO                |
| KM       |    506.912  |  465.46   |  1003.25   |     0.8502 |   0.8011 |    0.3906 | NO                |

## Regression Ceiling
**V1.3 REGRESSION CEILING REACHED** — ortalama MAE iyileşmesi -1.99%, R² kazancı DAYS +0.0134 / KM -0.0344.

## Survival Implications
**V2_SURVIVAL = STILL RECOMMENDED**. V1 regression yalnız observed target kullanır; censored snapshotlar
(TRAIN dışı olay dahil) hâlâ dışarıda ve observed/censored shift material.

## Final Verdict
**NO IMPROVEMENT**. Dataset FROZEN; R² yükseltmek için generator/target/noise/future-feature/TEST-tuning yapılmadı.
