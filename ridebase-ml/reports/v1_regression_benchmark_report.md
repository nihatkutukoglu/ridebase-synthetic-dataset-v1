# Executive Summary

V1 observed-only klasik regression benchmarkı tamamlandı. Days için **HistGradientBoostingRegressor**, km için **HistGradientBoostingRegressor** Validation ACTIONABLE MAE ile seçildi. TEST seçimde kullanılmadı.

# Problem Definition

İki ayrı supervised regression problemi vardır: sonraki servise kalan gün ve kilometre. Sonuçlar sentetik v1.2 offline benchmarkıdır.

# Dataset

Dataset/generator: 1.2.0. Toplam 41,518 snapshot; TRAIN/VALIDATION/TEST: 27,428 / 6,399 / 7,691.

# Observed-Only Regression Contract

V1 eligible days satırları TRAIN/VALIDATION/TEST = 20,679 / 1,932 / 2,622. Km geçerli satırları = 20,678 / 1,931 / 2,622.

# Why Censored Rows Are Excluded

Censored kaydın gerçek next-service hedefi bilinmez; 0/-1 veya censor süresi vermek hedefi bozar. Bu satırlar V1 hata metriklerine alınmadı.

# Preprocessing

05 artifactı kullanıldı: 127 ham → 277 encoded feature, TRAIN-only fit, sparse çıktı. LazyPredict dense float32 kopyasının tahmini RAM maliyeti 23.89 MiB idi.

# Global Median Baseline

Yalnız TRAIN hedef medyanları kullanıldı; TEST istatistiği öğrenilmedi.

# Segment Median Baseline

TRAIN'de n≥50 `category + usage_type` medyanı, unseen segmentte global TRAIN fallback kullanıldı.

# LazyPredict Screening

Days/Km başarılı model sayıları 20 / 19. Pahalı kernel, neighbors ve bazı CV modelleri runtime güvenliğiyle atlandı. LazyPredict yalnız aday taradı; final estimator değildir.

# Validation Model Selection

Ana metrik ACTIONABLE MAE, ikincil metrik Median AE. Days top 5: HistGradientBoostingRegressor, GradientBoostingRegressor, LinearSVR, XGBRegressor, PoissonRegressor. Km top 5: HistGradientBoostingRegressor, GradientBoostingRegressor, PassiveAggressiveRegressor, BayesianRidge, PoissonRegressor.

# Final Days Model

HistGradientBoostingRegressor; Validation MAE 22.471. Seçim TEST görülmeden yapıldı.

# Final Km Model

HistGradientBoostingRegressor; Validation MAE 1482.750. Seçim TEST görülmeden yapıldı.

# Test Results

Days MAE/Median AE/RMSE/R²: 23.042 / 17.758 / 30.747 / 0.417. Km: 1520.154 / 1069.467 / 2166.877 / 0.236.

# V0 vs V1

V0→V1 MAE improvement: days 65.82%, km 66.33%. V0 TEST R² (aynı observed satırlardan sonradan hesaplandı): days -2.793, km -3.320.

# Segment Analysis

`v1_regression_segment_metrics.csv` içinde kullanım, yoğunluk, marka, kategori, yaş, odometre, servis geçmişi, workshop ve model segmentleri vardır. n<50 gruplar sıralama için yorumlanmaz.

# Error Analysis

En büyük 20 days ve km hatası geçmiş/snapshot-time bağlamıyla kaydedildi; future bilgi kullanılmadı.

# Feature Importance

Validation permutation importance ve Ridge katsayı sanity kontrolü kaydedildi. Importance ilişkiyi gösterir, causality değildir.

# Overfitting Check

| target   |   train_mae |   validation_mae |   test_mae |   validation_minus_train |   test_minus_validation | overfitting_warning   |
|:---------|------------:|-----------------:|-----------:|-------------------------:|------------------------:|:----------------------|
| DAYS     |     67.6472 |          22.4714 |    23.0416 |                 -45.1758 |                0.570224 | NO                    |
| KM       |   2987.83   |        1482.75   |  1520.15   |               -1505.08   |               37.4037   | NO                    |

# Limitations

Sentetik/offline sonuçtur; production feature availability doğrulanmadı. Observed-only seçim yanlılığı olabilir. TEST tek zaman dilimidir ve tuning yapılmadı.

# V2 Survival Motivation

V1 yalnız 25,233 observed snapshotı kullanabilir. V2 Survival, 41,518 snapshotın tamamındaki observed + censored süre bilgisini kaybetmeden kullanabilir; V1 iyi olsa da denenmesi gereklidir.

# Final Verdict

Days MAE improvement 65.82%; km MAE improvement 66.33%. Validation→TEST farkları days 0.570, km 37.404. Production readiness hâlâ BLOCKED.
