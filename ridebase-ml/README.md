# RideBase ML — Synthetic Dataset v1.2

Bu çalışma alanının authoritative veri kaynağı repository kökündeki
`ridebase_v1_2/` klasörüdür. Notebooklar `source_tables/` ve
`derived_outputs/` dosyalarını doğrudan bu immutable release klasöründen okur.

`ridebase-ml/data/` altında eski çalışma kopyaları bulunabilir; bunlar v1.2
analizlerinde kullanılmaz ve authoritative kaynak kabul edilmez.

## Ana ML Problemleri

1. Bir sonraki servise kalan gün tahmini
2. Bir sonraki servise kalan kilometre tahmini
3. Bir sonraki serviste yapılacak bakım işlemlerinin tahmini
4. Right-censoring / survival analizi

## Proje Yapısı

```
ridebase-ml/
├── data/
│   ├── raw/source_tables/         # Legacy çalışma kopyaları; authoritative değil
│   ├── processed/derived_outputs/ # Legacy çalışma kopyaları; authoritative değil
│   └── interim/                   # Ara işlem çıktıları
├── notebooks/
├── src/{data,features,models,utils}/
├── reports/{figures,tables}/
├── models/
└── outputs/
```

## Notebook Sırası

1. `01_data_understanding.ipynb` — RideBase v1.2 dosya yapısı, tablolar,
   sütunlar, metadata ve temel kalite kontrolleri.
2. `02_eda.ipynb` — RideBase v1.2 EDA, reliability gerçekçilik analizi,
   survival hedefleri ve service-task title envanteri.
3. `03_production_feasibility.ipynb` — Issue #579 için read-only production
   export keşfi, veri kalitesi, target/mapping fizibilitesi ve Stage 1
   acceptance kontrolleri. Production extract yoksa açıkça `BLOCKED` kalır.
4. `04_v0_rule_baseline.ipynb` — Deterministic rule-based maintenance baseline
   for next-service timing and next-task prediction. Sonuçlar yalnız sentetik
   v1.2 offline benchmark'tır; production validation değildir.
5. `05_ml_preprocessing.ipynb` — Leakage-safe, train-only preprocessing, null
   semantics, encoding, scaling and model-ready target contracts for V1/V2/V3
   models. Model eğitmez; reusable preprocessor ve eligibility manifest üretir.
6. `06_v1_regression_benchmark.ipynb` — LazyPredict-assisted classical
   regression benchmark for observed next-service days/km targets, compared
   against the V0 rule baseline.
7. `07_v1_advanced_regression.ipynb` — Advanced leakage-safe regression with
   feature engineering, tuned boosting models and ensemble experiments for
   next-service days/km prediction.
8. `08_v1_target_engineering.ipynb` - Target-definition experiments for next-service regression: raw, log, residual, normalized, historical-deviation and next-periodic-maintenance targets.

Sonraki aşamalardaki feature engineering ve modelleme notebookları aynı
authoritative split üzerinde V0 baseline ile karşılaştırılacaktır.

10. `10_v1_3_final_regression.ipynb` — Final leakage-safe regression benchmark on RideBase Synthetic Dataset v1.3 using advanced boosting, native categorical modeling and validation-selected ensembles.
12. `12_v1_final_hyperparameter_tuning.ipynb` — Final temporal-CV Optuna hyperparameter tuning round for V1 next-service DAYS/KM regression on frozen RideBase v1.3 (HGB/LightGBM/XGBoost/CatBoost, target-specific feature selection, validation-selected blend); measures remaining model-level headroom.
13. `13_v2_survival_data_prep.ipynb` — Constructs leakage-safe time-to-next-service survival episodes from frozen RideBase v1.3, retaining right-censored observations and auditing temporal / censoring structure. **V2 status: DATA PREPARATION.**
14. `14_v2_survival_baseline.ipynb` — Fits and evaluates first leakage-safe time-to-next-service survival baselines (Kaplan-Meier reference, Cox PH, Random Survival Forest) using all observed and right-censored v1.3 service episodes.
15. `15_v2_survival_advanced.ipynb` — Tunes and calibrates advanced leakage-safe time-to-next-service survival models on frozen RideBase v1.3, optimizing horizon probability quality, calibration, temporal generalization and motorcycle-grouped evaluation.
16. `16_v2_production_packaging.ipynb` — Packages the frozen FULL/FINAL V2 survival ensemble and calibration artifacts into a deterministic production inference service, API contract and RideBase Control Center module without retraining.
11. `11_v1_external_maintenance_knowledge.ipynb` — External manufacturer maintenance schedule features for leakage-safe A/B evaluation of next-service KM/DAYS regression on frozen RideBase v1.3.

## Kurulum

```bash
pip install -r requirements.txt
```