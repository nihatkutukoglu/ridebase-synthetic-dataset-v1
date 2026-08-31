# Executive Summary

Final DAYS: **Manual::WeightedBlend** — TEST MAE 20.805, R² 0.4379. Final KM: **AutoGluon::WeightedEnsemble_L2** — TEST MAE 1402.565, R² 0.1386. Karar: **AUTOML FOUND MODERATE HEADROOM**. Production validation **BLOCKED**.

# Research Question

Raw next-any-service target değişmeden native categorical AutoML, boosting ve weighted ensemble anlamlı performans artışı sağlıyor mu?

# Existing V1 Results

V1 Advanced TEST: DAYS MAE 22.206, R² 0.4349; KM MAE 1510.176, R² 0.2481.

# Data Contract

Dataset/generator 1.2.0; 41,518 snapshot. Observed DAYS {'TRAIN': 20679, 'VALIDATION': 1932, 'TEST': 2622}; valid KM {'TRAIN': 20678, 'VALIDATION': 1931, 'TEST': 2622}. Censored hedefler uydurulmadı.

# Raw vs Encoded Features

Raw 127 feature; encoded 277 feature. DAYS winner: RAW_NATIVE_CATEGORICAL; KM winner: RAW_NATIVE_CATEGORICAL.

# AutoML Setup

AutoGluon 1.6.1; target başına 15 dakika üst sınır; explicit TRAIN/tuning_data VALIDATION; MAE primary; random holdout/bagging/stacking kapalı. AutoML sihir değildir.

# Native Categorical Models

CatBoost, LightGBM, XGBoost, RandomForest ve ExtraTrees tarandı. Kategoriler raw category/string semantiğiyle verildi.

# AutoML Leaderboard

DAYS 10, KM 10 model/ensemble kaydı. Framework skorları kendi predictionlarımızdan yeniden hesaplandı.

# CatBoost Experiment

DAYS MAE=20.900; KM MAE=1509.215. RMSE internal loss, MAE early-stopping metric; final ölçüm original target scale.

# LightGBM Experiment

DAYS MAE=22.159; KM MAE=1456.357.

# XGBoost Experiment

DAYS MAE=21.629; KM MAE=1432.138.

# Model Diversity

Prediction korelasyonları target bazında kaydedildi. Çok yüksek korelasyon ensemble headroom'unu sınırlar.

# Weighted Ensemble

DAYS AutoGluon: AutoGluon::WeightedEnsemble_L2: MAE=20.929, R2=0.2819. KM AutoGluon: AutoGluon::WeightedEnsemble_L2: MAE=1406.367, R2=0.0942. Manual constrained blend validation MAE ile, weights>=0 ve toplam=1 koşuluyla seçildi.

# Validation Selection

DAYS Manual::WeightedBlend; KM AutoGluon::WeightedEnsemble_L2. TEST görülmeden kilitlendi.

# Final TEST Results

DAYS: MAE 20.805, Median AE 14.157, RMSE 30.197, R² 0.4379, bias -0.715, P90 AE 48.732, ±30 80.130%, ±60 93.364%.

KM: MAE 1402.565, Median AE 656.804, RMSE 2300.138, R² 0.1386, bias -587.875, P90 AE 3859.505, ±1000 61.747%, ±2000 77.422%.

# V0 vs Basic V1 vs Advanced V1 vs AutoML

Tam tablo `reports/tables/v1_automl_vs_previous_models.csv` dosyasındadır. AutoML TEST seçimi değiştirmedi.

# Feature Importance

Top-20 raw permutation importance kaydedildi. Importance causality değildir.

# Error Analysis

History depth, usage, age, odometer, category/model ve interval variability segmentleri ile en büyük hatalar kaydedildi.

# Leakage Audit

Tüm kontroller PASS. Target/future X'te yok; TEST fit/weight selection'da yok; preprocessing TRAIN-fitted; censored pseudo-target yok.

# Reproducibility

Seed 42; deterministic prediction replay DAYS=True, KM=True.

# Limitations

Sentetik offline PoC; production validation BLOCKED. V1 observed-only seçim yanlılığı taşır. Quantile deney secondary'dir.

# Regression Ceiling Assessment

**AUTOML FOUND MODERATE HEADROOM**

# V2 Survival Implications

Bu V1 notebook 16,285 censored/cutoff-ineligible snapshotı regression targetı olarak kullanmaz. AutoML güçlü olsa bile V2 Survival ihtiyacı ortadan kalkmaz.

# Final Verdict

Birincil karar MAE, sonra Median AE, R², tolerance ve temporal stability ile verilmiştir. Target engineering ile kıyas bu notebookun kapsamı dışındadır.
