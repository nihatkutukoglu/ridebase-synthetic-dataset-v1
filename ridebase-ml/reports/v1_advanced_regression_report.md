# Executive Summary

Advanced V1 tamamlandı. DAYS final: **ENSEMBLE__INVERSE_VALIDATION_MAE_BLEND**; KM final: **GradientBoostingRegressor__RAW**. Basic V1'e göre TEST MAE değişimi DAYS 3.63%, KM 0.66%. Production validation **BLOCKED**.

# Why Advanced Regression

Amaç leakage-free snapshot/history featurelarıyla observed-only regression sınırını ölçmektir; R² hedefi zorlanmamıştır.

# Existing V1 Baseline

DAYS Basic MAE/R²: 23.042/0.417. KM: 1520.154/0.236.

# Feature Engineering

Var olan 05 featureları tekrar üretilmedi. 51 yeni ham feature; service rolling 2/5/expanding, tamamlanmış-ay usage trendleri, maintenance/failure oranları, policy-derived due ve sınırlı interaction gruplarında üretildi.

# Leakage Controls

Her engineered feature `period/service <= snapshot_at` sözleşmesindedir. Policy due, actual next service değildir. Audit: 51/51 PASS. TEST tuning/seçimde kullanılmadı.

# Feature Ablation

| feature_set               |   feature_count | notes                                                     |   days_val_mae |   days_val_r2 |   km_val_mae |   km_val_r2 |   incremental_gain |
|:--------------------------|----------------:|:----------------------------------------------------------|---------------:|--------------:|-------------:|------------:|-------------------:|
| SET_A_BASE_05             |             277 | Same default HistGradientBoosting family; full Validation |        22.4714 |      0.283081 |      1482.75 |    0.152122 |          0         |
| SET_B_SERVICE_HISTORY     |             306 | Same default HistGradientBoosting family; full Validation |        22.4012 |      0.275114 |      1536.07 |    0.14218  |          0.0701906 |
| SET_C_USAGE_TRENDS        |             319 | Same default HistGradientBoosting family; full Validation |        23.4014 |      0.252984 |      1501.84 |    0.145342 |         -1.0002    |
| SET_D_MAINTENANCE_FAILURE |             338 | Same default HistGradientBoosting family; full Validation |        23.5514 |      0.267477 |      1482.65 |    0.158636 |         -0.150047  |
| SET_E_INTERACTIONS        |             348 | Same default HistGradientBoosting family; full Validation |        23.0392 |      0.27129  |      1497.14 |    0.153457 |          0.512217  |

# Target Distribution

| target   |     n |     mean |   median |      std |   skewness |       p95 |       p99 |      max |
|:---------|------:|---------:|---------:|---------:|-----------:|----------:|----------:|---------:|
| DAYS     | 20679 |  159.569 |  111.953 |  151.178 |    2.23161 |   450.921 |   744.912 |  1343.89 |
| KM       | 20678 | 6762.51  | 5267.5   | 5032.12  |    2.33602 | 16560.9   | 25613.2   | 63341    |

# Target Transformation

DAYS: RAW; KM: RAW. Raw ve log1p aynı Validation metrikleriyle karşılaştırıldı.

# Model Families

HistGradientBoosting, ExtraTrees, RandomForest, GradientBoosting, XGBoost, LightGBM ve CatBoost değerlendirildi. Availability/training durumu `v1_advanced_model_status.csv` içindedir.

# Hyperparameter Tuning

TRAIN zamana göre sıralandı; iki expanding fold ve her ailede iki kontrollü RandomizedSearchCV örneği kullanıldı. Primary CV metric negative MAE'dir.

# Ensemble Experiments

| target   | ensemble_name                | members                                                                                  | weights                        |   validation_mae |   validation_r2 | selected   |
|:---------|:-----------------------------|:-----------------------------------------------------------------------------------------|:-------------------------------|-----------------:|----------------:|:-----------|
| DAYS     | SIMPLE_AVERAGE               | GradientBoostingRegressor__RAW | LGBMRegressor__RAW | HistGradientBoostingRegressor__RAW | [0.333333, 0.333333, 0.333333] |          21.7293 |        0.317003 | False      |
| DAYS     | INVERSE_VALIDATION_MAE_BLEND | GradientBoostingRegressor__RAW | LGBMRegressor__RAW | HistGradientBoostingRegressor__RAW | [0.347257, 0.332021, 0.320723] |          21.6965 |        0.317002 | True       |
| KM       | SIMPLE_AVERAGE               | GradientBoostingRegressor__RAW | HistGradientBoostingRegressor__RAW | LGBMRegressor__RAW | [0.333333, 0.333333, 0.333333] |        1486.05   |        0.139293 | False      |
| KM       | INVERSE_VALIDATION_MAE_BLEND | GradientBoostingRegressor__RAW | HistGradientBoostingRegressor__RAW | LGBMRegressor__RAW | [0.341848, 0.333315, 0.324837] |        1485.39   |        0.140194 | False      |

# Validation Selection

DAYS Validation MAE: 21.697; KM: 1473.693. Feature set/model/transform/blend seçimleri TEST açılmadan kilitlendi.

# Final Test Results

DAYS MAE/Median AE/RMSE/R²: 22.206/16.555/30.277/0.435. KM: 1510.176/1091.475/2148.939/0.248.

# V0 vs V1 vs Advanced V1

| target   | metric      |      V0 Rule |   V1 Advanced |    V1 Basic |
|:---------|:------------|-------------:|--------------:|------------:|
| DAYS     | mae         |   67.4105    |     22.2058   |   23.0416   |
| DAYS     | median_ae   |   57.8479    |     16.5551   |   17.7582   |
| DAYS     | r2          |   -2.79343   |      0.434891 |    0.417213 |
| DAYS     | within_30   |    0.17315   |      0.783371 |    0.763921 |
| DAYS     | within_60   |    0.519832  |      0.942029 |    0.937834 |
| KM       | mae         | 4515.31      |   1510.18     | 1520.15     |
| KM       | median_ae   | 3981.5       |   1091.47     | 1069.47     |
| KM       | r2          |   -3.31962   |      0.248144 |    0.23554  |
| KM       | within_1000 |    0.0339436 |      0.463768 |    0.471777 |
| KM       | within_2000 |    0.0652174 |      0.753623 |    0.764683 |

# Feature Importance

Top 20 permutation importance kaydedildi. Importance, causality değildir.

# Error Analysis

En büyük 20 DAYS/KM hatası ve history-depth segmentleri kaydedildi. En yüksek yeterli örnekli pattern: KM / 9+ (n=1357, MAE=1675.14).

# Observed vs Censored Population Shift

Shift durumu: **MATERIAL**. En büyük fark: annual_km_baseline (STANDARDIZED_MEAN_DIFFERENCE=0.747). Bu nedenle observed-only performans tüm population'a doğrudan genellenemez.

# Why R² Is Limited

DAYS R²<0.60: interval variance, müşteri gecikmesi, arıza rastlantısallığı ve observed-only selection incelenmelidir. KM R²<0.45: kullanım trendi dışındaki ölçülmeyen rota/aktivite ve failure etkileri sınır oluşturabilir. Target noise, stochastic service behavior, missing explanatory variables, unpredictable failures, generator randomness, interval variance ve observed-only seçim etkisi birlikte değerlendirilmelidir.

# Regression Ceiling Assessment

**DIMINISHING RETURNS**. Ortalama MAE iyileşmesi 2.14%, R² kazancı DAYS 0.018, KM 0.013; Validation→TEST farkları `v1_advanced_train_validation_test_gap.csv` içindedir.

# V2 Survival Motivation

V1 yalnız observed satırları regression targetı yapar. V2, 41.518 snapshotın observed+censored duration bilgisini birlikte kullanabildiği ve population shift material olduğu için hâlâ önerilir.

# Limitations

Sentetik v1.2 offline PoC; production validation yoktur. Validation tekrar model/feature/blend seçiminde kullanılmıştır. Censored targetlar V1 metriğine dahil değildir. Feature importance nedensellik değildir.

# Final Verdict

**SMALL IMPROVEMENT**. R² skorunu yükseltmek için future/target feature, TEST tuning, target uydurma veya outlier silme yapılmadı.
