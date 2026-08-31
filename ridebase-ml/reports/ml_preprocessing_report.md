# Executive Summary

RideBase Synthetic Dataset v1.2 için leakage-safe, TRAIN-only preprocessing artifact'ı hazırlandı. Model eğitilmedi. Production validation hâlâ BLOCKED.

# Dataset and Split

- Dataset/generator version: 1.2.0
- Total snapshots: 41,518
- TRAIN / VALIDATION / TEST: 27,428 / 6,399 / 7,691
- Split source: `split_manifest.csv`; random split kullanılmadı.

# Feature / Target Separation

Ana feature kaynağı `ml_maintenance_snapshots.parquet`tir. Next-service ve next-task tabloları yalnız target/eligibility için kullanılır; X feature matrisine girmez.

# Leakage Audit

Snapshot feature setinde future/target kolon bulunmadı. Identifier, raw datetime, metadata, constant ve açık redundant alanlar X'ten çıkarıldı. Target tabloları evaluation/target-only olarak işaretlendi.

# Null Semantics

Candidate feature'larda yalnız 3 kolon ve 40,096 boş hücre vardır. Target NULL'ları censoring anlamını korur ve doldurulmaz.

# Numeric Features

95 numeric feature vardır. Outlier satırları otomatik silinmedi.

# Categorical Features

24 categorical feature TRAIN kategorileriyle one-hot edilir. Unseen validation/test kategorileri `handle_unknown=ignore` ile güvenli işlenir.

# Imputation Strategy

`engine_displacement_cc`, `engine_oil_service_qty_l`, `spark_plug_count` structural/unknown master NULL'ları `-1 + missing indicator` alır. TRUE_MISSING numeric candidate olmadığı için bu sürümde median fill uygulanmaz. Categorical pipeline gelecekteki gerçek missing için `UNKNOWN` hazırlar; mevcut v1.2'de categorical NULL yoktur.

# Encoding Strategy

Makul cardinality kategoriler OneHotEncoder ile çevrilir. Yüksek cardinality entity/customer/service kimlikleri model X'inden çıkarılır.

# Scaling Strategy

Numeric feature'lar StandardScaler ile yalnız TRAIN üzerinde fit edilir. Booleanlar 0/1 kalır. Tree modeller için ileride scalersız ayrı transformer kurulabilir.

# Constant / Near-Constant Features

5 constant feature çıkarıldı. 7 non-constant feature ≥99% dominant olduğu için işaretlendi fakat rare operational signal olabileceğinden otomatik çıkarılmadı.

# Final Feature Set

- Raw model feature: 127
- Encoded feature dimension: 277
- Sparse matrix: YES
- Feature NaN after transform: 0

# Survival Target Contract

V2 tüm 41,518 snapshotı duration + event_observed ile kullanabilir: 25,233 event ve 16,285 censored.

# Statistical Target Contract

V1 yalnız split cutoff içinde observed next-service satırlarını kullanır: TRAIN/VAL/TEST = 20,679 / 1,932 / 2,622.

# Multi-Label Target Contract

V3 98 canonical task label kullanır ve yalnız observed/eligible satırları alır. Censored label NULL'ları korunur.

# Train-Only Fit Validation

Scaler mean, encoder categories, imputer contract ve reload kontrolü PASS. Validation/test yalnız transform edildi.

# Model-Ready Dataset Summary

Reusable preprocessor: `ml_preprocessor_v1_2.joblib`. Lightweight index/target-mask contract: `ml_modeling_manifest.parquet`.

# Limitations

- Sonuçlar sentetik v1.2 içindir; production performance değildir.
- Production feature availability ayrıca doğrulanmalıdır.
- Ortak preprocessing feature dönüşümünü paylaşır; V1/V2/V3 target ve satır maskeleri aynı değildir.
- Tree modeller scaling istemeyebilir ve ayrı transformer artifact'ı gerektirebilir.

# Final Verdict

V1/V2/V3 model notebooklarına leakage-free sentetik feature/target contractı sağlandı: **YES**. Production readiness: **BLOCKED**.
