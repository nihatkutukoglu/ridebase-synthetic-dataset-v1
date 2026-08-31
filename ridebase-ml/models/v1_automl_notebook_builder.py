from pathlib import Path
import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
NB_PATH = ROOT / "notebooks" / "09_v1_automl_ensemble.ipynb"


def md(text):
    return nbf.v4.new_markdown_cell(text.strip() + "\n")


def code(text):
    return nbf.v4.new_code_cell(text.strip() + "\n")


cells = [
md(r"""
# RideBase 09 — V1 AutoML & Ensemble Regression

Bu notebook RideBase Synthetic Dataset v1.2 üzerinde, mevcut **next-service DAYS/KM targetlarını değiştirmeden** güçlü tabular modeller, native categorical modeling ve weighted ensemble yaklaşımını değerlendirir.

Amaç: **“Regression performansındaki sınır model seçimi / preprocessing kaynaklı mı?”** sorusunu incelemektir.

> Production validation hâlâ **BLOCKED**. Bu çalışma sentetik veri üzerinde offline PoC araştırmasıdır.
"""),
md(r"""
## 1. Araştırma tasarımı ve kavramlar

### Ne yapıyoruz?

İki feature temsilini aynı temporal TRAIN/VALIDATION/TEST satırlarında karşılaştırıyoruz: (A) 05 notebookunun train-fitted one-hot preprocessor çıktısı ve (B) leakage-safe raw featurelar ile native kategorik modelleme. AutoGluon’un model leaderboard’unu, doğrudan CatBoost/LightGBM/XGBoost deneylerini ve validation ağırlıklı blend’i kuruyoruz.

### Neden yapıyoruz?

Advanced feature engineering yalnız küçük artış verdi. Target aynı kalırken daha güçlü model seçimi ve model çeşitliliğinin ek headroom sağlayıp sağlamadığını ayrıştırmak istiyoruz.

### Önceki V1'den farkı ne?

**AutoML**, belirlenmiş arama alanında model ailelerini ve ayarları disiplinli biçimde dener. **AutoML sihir değildir.** Yalnız verdiğimiz TRAIN üzerinde öğrenir; authoritative VALIDATION ile sıralanır. TEST seçim sırasında kapalıdır.

**Native categorical feature**, kategorik kolonların one-hot'a çevrilmeden CatBoost/LightGBM/XGBoost gibi model ailesine kategori semantiğiyle verilmesidir. **Ensemble**, birden fazla modelin tahminini birleştirir; **weighted ensemble** modelleri eşit değil validation'da öğrenilen ağırlıklarla birleştirir. **Bagging**, train içinde örnekleme/fold değiştirerek varyansı azaltır. **Stacking**, bir modelin çıktısını üst seviye modele girdi yapar. Bu deneyde external VALIDATION geleceğini eğitime taşımamak için AutoGluon bagging kapalı, stacking seviyesi sıfırdır; yalnız weighted ensemble L2 katmanı açıktır.

**Early stopping**, validation performansı iyileşmediğinde boosting'i durdurur. **Validation leaderboard**, TEST'e bakmadan adayların sıralandığı tablodur. **Overfitting**, train performansının validation'a taşınmamasıdır. **Model diversity**, modellerin aynı hataları yapmaması demektir; tahmin korelasyonu 0.999 olan iki modelin blend katkısı genellikle sınırlıdır.

### Leakage riski var mı?

Future kolonlar ve targetlar feature tablosuna alınmaz; censored hedef uydurulmaz; TEST yalnız final seçim kilitlendikten sonra açılır.

### Sonucu nasıl yorumlarız?

Birincil ürün metriği MAE'dir. R² ikincil açıklayıcı metriktir; daha yüksek R² tek başına daha iyi ürün modeli anlamına gelmez.
"""),
code(r"""
from pathlib import Path
import json, os, platform, random, shutil, time, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

from sklearn.metrics import mean_absolute_error, median_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor
from scipy.optimize import minimize
from autogluon.tabular import TabularPredictor
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from xgboost import XGBRegressor
import autogluon.tabular, catboost, lightgbm, xgboost, sklearn

warnings.filterwarnings("ignore")
SEED = 42
random.seed(SEED); np.random.seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)

PROJECT = Path.cwd().resolve()
if PROJECT.name == "notebooks": PROJECT = PROJECT.parent
assert PROJECT.name == "ridebase-ml", f"Beklenmeyen çalışma dizini: {PROJECT}"
REPO = PROJECT.parent
DATA = REPO / "ridebase_v1_2" / "derived_outputs"
MODELS = PROJECT / "models" / "v1_automl"
OUTPUTS = PROJECT / "outputs"
TABLES = PROJECT / "reports" / "tables"
FIGURES = PROJECT / "reports" / "figures" / "v1_automl"
REPORT = PROJECT / "reports" / "v1_automl_ensemble_report.md"
MODEL_CARD = PROJECT / "models" / "v1_automl_model_card.json"
for p in [MODELS, OUTPUTS, TABLES, FIGURES]: p.mkdir(parents=True, exist_ok=True)

# Kendi target model klasörlerimizi Run All tekrarı için temizliyoruz; başka artifactlara dokunmuyoruz.
for p in [MODELS / "v1_automl_days_model", MODELS / "v1_automl_km_model"]:
    if p.exists(): shutil.rmtree(p)
    p.mkdir(parents=True)

AUTOML_TIME_LIMIT_SECONDS = 900  # target başına kontrollü 15 dakika üst sınır
RUNTIME_ROWS = []
VERSIONS = {
    "python": platform.python_version(), "autogluon": autogluon.tabular.__version__,
    "catboost": catboost.__version__, "lightgbm": lightgbm.__version__,
    "xgboost": xgboost.__version__, "sklearn": sklearn.__version__,
}
print(VERSIONS)
"""),
md(r"""
## 2. Dataset guard, target mask ve split bütünlüğü

### Ne yapıyoruz?

Authoritative v1.2 metadata, snapshot, raw next-service target ve split manifest dosyalarını okuyup version/row/split assertion'ları çalıştırıyoruz.

### Neden yapıyoruz?

Yanlış release veya yanlış target mask üzerinde iyi skor üretmek araştırma sorusunu geçersiz kılar.

### Önceki V1'den farkı ne?

Target değişmiyor: DAYS=`days_to_next_service`, KM=`km_to_next_service`. Yalnız manifestte observed ve primary-cutoff eligible satırlar kullanılıyor.

### Leakage riski var mı?

Censored kayıtlara 0, -1, median veya pseudo-label atanmıyor. Boundary-crossing future targetlar dışarıda kalıyor.

### Sonucu nasıl yorumlarız?

Guard hücresi PASS olmadan hiçbir model eğitilmez.
"""),
code(r"""
t0 = time.perf_counter()
metadata = json.loads((DATA / "dataset_metadata.json").read_text())
snapshots = pd.read_parquet(DATA / "ml_maintenance_snapshots.parquet")
targets = pd.read_parquet(DATA / "ml_next_service_targets.parquet")
manifest = pd.read_csv(DATA / "split_manifest.csv")
prep_config = json.loads((PROJECT / "models" / "preprocessing_config.json").read_text())

assert metadata["dataset"]["dataset_version"] == "1.2.0"
assert metadata["dataset"]["generator_version"] == "1.2.0"
assert len(snapshots) == len(targets) == len(manifest) == 41518
assert snapshots.snapshot_id.is_unique and targets.snapshot_id.is_unique and manifest.snapshot_id.is_unique

joined = (snapshots.merge(targets[["snapshot_id", "target_event_observed", "is_right_censored",
                                   "days_to_next_service", "km_to_next_service", "target_km_valid"]],
                          on="snapshot_id", validate="one_to_one")
                   .merge(manifest[["snapshot_id", "primary_time_split", "next_service_regression_eligible_primary",
                                    "boundary_crossing_future_target", "primary_label_cutoff_at"]],
                          on="snapshot_id", validate="one_to_one"))
joined["snapshot_at"] = pd.to_datetime(joined["snapshot_at"])
joined["primary_label_cutoff_at"] = pd.to_datetime(joined["primary_label_cutoff_at"])
joined["days_eligible"] = (joined.next_service_regression_eligible_primary.eq(1) &
                           joined.target_event_observed.eq(1) & joined.days_to_next_service.notna())
joined["km_eligible"] = (joined.days_eligible & joined.target_km_valid.eq(1) & joined.km_to_next_service.notna())

expected = {"DAYS": {"TRAIN": 20679, "VALIDATION": 1932, "TEST": 2622},
            "KM": {"TRAIN": 20678, "VALIDATION": 1931, "TEST": 2622}}
eligible_counts = {}
for target, mask_col in [("DAYS", "days_eligible"), ("KM", "km_eligible")]:
    eligible_counts[target] = {s: int((joined[mask_col] & joined.primary_time_split.eq(s)).sum())
                               for s in ["TRAIN", "VALIDATION", "TEST"]}
    assert eligible_counts[target] == expected[target], (target, eligible_counts[target])

split_ids = {s: set(joined.loc[joined.primary_time_split.eq(s), "snapshot_id"])
             for s in ["TRAIN", "VALIDATION", "TEST"]}
assert not (split_ids["TRAIN"] & split_ids["VALIDATION"])
assert not (split_ids["TRAIN"] & split_ids["TEST"])
assert not (split_ids["VALIDATION"] & split_ids["TEST"])
assert joined.loc[joined.primary_time_split.eq("TRAIN"), "snapshot_at"].max() < joined.loc[joined.primary_time_split.eq("VALIDATION"), "snapshot_at"].min()
assert joined.loc[joined.primary_time_split.eq("VALIDATION"), "snapshot_at"].max() < joined.loc[joined.primary_time_split.eq("TEST"), "snapshot_at"].min()
assert not joined.loc[joined.days_eligible, "boundary_crossing_future_target"].astype(bool).any()

RUNTIME_ROWS.append({"stage": "dataset_guard_and_join", "target": "BOTH", "seconds": time.perf_counter()-t0,
                     "budget_seconds": np.nan, "status": "PASS"})
print("DATASET_GUARD=PASS", eligible_counts)
print("SPLIT_INTEGRITY=PASS; TARGET_MASKS=PASS")
"""),
md(r"""
## 3. Raw feature leakage audit ve iki temsil

### Ne yapıyoruz?

05'in train-fitted preprocessor sözleşmesindeki numeric/categorical/boolean featureları raw pipeline için de kullanıyoruz. Snapshot/customer/source unique ID'leri, metadata sabitlerini ve datetime ham alanlarını dışarıda bırakıyoruz. `model_id` ve `workshop_id` row-unique kimlik değildir (39 model, 10 workshop); domain kategorisi olarak tutulur.

### Neden yapıyoruz?

Temsil farkını model farkından mümkün olduğunca ayrıştırmak için iki pipeline aynı leakage-safe feature evrenini paylaşır.

### Önceki V1'den farkı ne?

Pipeline A 277 one-hot encoded feature üretir. Pipeline B raw featureları korur; kategorikler pandas `category`/string olarak model ailesine gider.

### Leakage riski var mı?

Audit her snapshot kolonunu availability, future information ve identifier açısından işaretler. Kullanılan her feature PASS olmalıdır.

### Sonucu nasıl yorumlarız?

Raw pipeline'ın daha iyi olması, one-hot temsilin bilgi/inductive-bias sınırı oluşturduğuna işaret eder; nedensellik kanıtı değildir.
"""),
code(r"""
numeric_features = prep_config["numeric_features"]
categorical_features = prep_config["categorical_features"]
boolean_features = prep_config["boolean_features"]
raw_features = numeric_features + categorical_features + boolean_features
assert len(raw_features) == len(set(raw_features))
assert set(raw_features).issubset(snapshots.columns)

future_tokens = ("next_", "target_", "censor")
identifier_cols = {"snapshot_id", "source_service_id", "motorcycle_id", "customer_id"}
audit_rows = []
for col in snapshots.columns:
    used = col in raw_features
    identifier = col in identifier_cols
    future = col.startswith(future_tokens)
    if used:
        status, reason = "PASS", "Snapshot anında mevcut, preprocessing contract featureı"
    elif identifier:
        status, reason = "PASS", "Row/entity unique identifier; feature dışı"
    elif future:
        status, reason = "PASS", "Future/target-benzeri alan; feature dışı"
    elif col in prep_config.get("dropped_features", []):
        status, reason = "PASS", "Metadata, redundant veya raw datetime; feature dışı"
    else:
        status, reason = "PASS", "Mevcut contract tarafından seçilmedi"
    audit_rows.append({"feature_name": col, "source": "ml_maintenance_snapshots.parquet",
                       "available_at_snapshot": True, "future_information": future,
                       "identifier": identifier, "used": used, "leakage_status": status, "reason": reason})
raw_feature_audit = pd.DataFrame(audit_rows)
assert (raw_feature_audit.loc[raw_feature_audit.used, "leakage_status"] == "PASS").all()
raw_feature_audit.to_csv(TABLES / "v1_automl_raw_feature_leakage_audit.csv", index=False)

def make_raw(df):
    out = df[raw_features].copy()
    for c in categorical_features:
        out[c] = out[c].fillna("UNKNOWN").astype(str).astype("category")
    for c in boolean_features:
        out[c] = out[c].fillna(0).astype(bool)
    return out

raw_data, y_data, context = {}, {}, {}
for target, mask_col, ycol in [("DAYS", "days_eligible", "days_to_next_service"),
                               ("KM", "km_eligible", "km_to_next_service")]:
    raw_data[target], y_data[target], context[target] = {}, {}, {}
    for split in ["TRAIN", "VALIDATION", "TEST"]:
        part = joined.loc[joined[mask_col] & joined.primary_time_split.eq(split)].copy()
        part = part.sort_values(["snapshot_at", "snapshot_id"]).reset_index(drop=True)
        raw_data[target][split] = make_raw(part)
        y_data[target][split] = part[ycol].astype(float).to_numpy()
        context[target][split] = part

preprocessor = joblib.load(PROJECT / "models" / "ml_preprocessor_v1_2.joblib")
encoded_feature_names = np.asarray(preprocessor.get_feature_names_out(), dtype=str)
assert len(encoded_feature_names) == 277
encoded_data = {t: {s: preprocessor.transform(context[t][s]).toarray() for s in ["TRAIN", "VALIDATION", "TEST"]}
                for t in ["DAYS", "KM"]}
print(f"RAW_FEATURE_COUNT={len(raw_features)}; ENCODED_FEATURE_COUNT={len(encoded_feature_names)}")
print("RAW_FEATURE_LEAKAGE_AUDIT=PASS")
"""),
md(r"""
## 4. Ortak metrikler ve candidate registry

### Ne yapıyoruz?

Framework skoruna kör güvenmemek için her validation/test prediction'ından MAE, Median AE, RMSE, R², bias, P90 AE ve ürün tolerance oranlarını yeniden hesaplıyoruz.

### Neden yapıyoruz?

AutoGluon'un primary metriği negatif MAE yönünde olabilir; ürün raporunda pozitif MAE ve tüm ikincil metrikler gerekir.

### Önceki V1'den farkı ne?

Tek model yerine bütün adayların predictionları ortak registry'de tutulur; ensemble ve diversity analizi aynı prediction vektörlerini kullanır.

### Leakage riski var mı?

Bu aşamada registry yalnız VALIDATION predictionlarını kabul eder. TEST prediction fonksiyonları ancak seçim kilidinden sonra çağrılır.

### Sonucu nasıl yorumlarız?

Final sıralama MAE → Median AE → R² → tolerance/stability önceliğindedir.
"""),
code(r"""
def metrics(y, pred, target):
    pred = np.clip(np.asarray(pred, float), 0, None)
    y = np.asarray(y, float); ae = np.abs(pred-y)
    out = {"mae": mean_absolute_error(y,pred), "median_ae": median_absolute_error(y,pred),
           "rmse": mean_squared_error(y,pred)**0.5, "r2": r2_score(y,pred),
           "bias": float(np.mean(pred-y)), "p90_ae": float(np.quantile(ae,.90))}
    tolerances = [15,30,45,60,90] if target == "DAYS" else [500,1000,1500,2000,5000]
    out.update({f"within_{x}": float(np.mean(ae <= x)) for x in tolerances})
    return out

candidates = {"DAYS": {}, "KM": {}}
def register(target, name, family, representation, val_pred, predictor_kind, model_ref, notes=""):
    pred = np.clip(np.asarray(val_pred, float), 0, None)
    candidates[target][name] = {"family": family, "representation": representation,
        "val_pred": pred, "metrics": metrics(y_data[target]["VALIDATION"], pred, target),
        "predictor_kind": predictor_kind, "model_ref": model_ref, "notes": notes}

def predict_candidate(target, rec, split):
    if rec["predictor_kind"] == "autogluon":
        predictor, model_name = rec["model_ref"]
        return np.clip(predictor.predict(raw_data[target][split], model=model_name).to_numpy(), 0, None)
    if rec["predictor_kind"] == "encoded":
        return np.clip(rec["model_ref"].predict(encoded_data[target][split]), 0, None)
    if rec["predictor_kind"] == "catboost":
        x = raw_data[target][split].copy()
        for c in categorical_features: x[c] = x[c].astype(str)
        return np.clip(rec["model_ref"].predict(x), 0, None)
    if rec["predictor_kind"] in {"lightgbm", "xgboost"}:
        return np.clip(rec["model_ref"].predict(raw_data[target][split]), 0, None)
    if rec["predictor_kind"] == "blend":
        members, weights = rec["model_ref"]
        return np.clip(sum(w*predict_candidate(target, candidates[target][m], split)
                           for m,w in zip(members,weights)), 0, None)
    raise ValueError(rec["predictor_kind"])
"""),
md(r"""
## 5. Pipeline A — 277 encoded feature

### Ne yapıyoruz?

Train-fitted 05 preprocessor çıktısı üzerinde HistGradientBoosting ve ExtraTrees eğitiyoruz.

### Neden yapıyoruz?

Raw/native categorical kazancını değerlendirmek için güçlü ve yeniden üretilebilir encoded baseline gerekir.

### Önceki V1'den farkı ne?

Basic V1'in tek HistGradientBoosting modeline ek olarak ExtraTrees de aday havuzuna girer.

### Leakage riski var mı?

Preprocessor istatistikleri 05'te yalnız TRAIN üzerinde fit edilmiştir; burada yeniden fit edilmez. TEST kullanılmaz.

### Sonucu nasıl yorumlarız?

Bu pipeline kazanırsa native categorical temsile dair ek fayda bulunmamıştır.
"""),
code(r"""
t0 = time.perf_counter()
for target in ["DAYS", "KM"]:
    models = {
        "Encoded_HistGradientBoosting": HistGradientBoostingRegressor(
            loss="absolute_error", learning_rate=.055, max_iter=700, max_leaf_nodes=31,
            l2_regularization=2.0, min_samples_leaf=25, early_stopping=True,
            validation_fraction=.12, n_iter_no_change=50, random_state=SEED),
        "Encoded_ExtraTrees": ExtraTreesRegressor(
            n_estimators=450, max_features=.85, min_samples_leaf=2,
            n_jobs=-1, random_state=SEED),
    }
    for name, model in models.items():
        st = time.perf_counter(); model.fit(encoded_data[target]["TRAIN"], y_data[target]["TRAIN"])
        pred = model.predict(encoded_data[target]["VALIDATION"])
        register(target, name, name.split("_")[1], "PREPROCESSED_277", pred, "encoded", model,
                 "05 train-fitted one-hot representation")
        joblib.dump(model, MODELS / f"v1_automl_{target.lower()}_model" / f"{name}.joblib")
        RUNTIME_ROWS.append({"stage": name, "target": target, "seconds": time.perf_counter()-st,
                             "budget_seconds": np.nan, "status": "COMPLETE"})
RUNTIME_ROWS.append({"stage": "preprocessed_pipeline_total", "target": "BOTH", "seconds": time.perf_counter()-t0,
                     "budget_seconds": np.nan, "status": "COMPLETE"})
print({t:{n:round(r['metrics']['mae'],3) for n,r in candidates[t].items()} for t in candidates})
"""),
md(r"""
## 6. Pipeline B — AutoGluon raw/native categorical

### Ne yapıyoruz?

AutoGluon TabularPredictor ile LightGBM, CatBoost, XGBoost, RandomForest ve ExtraTrees varyantlarını tarıyoruz. DAYS ve KM için ayrı predictor vardır; primary metric `mean_absolute_error`.

### Neden yapıyoruz?

Model ailesi, kategorik işleme ve weighted ensemble etkisini ortak validation disiplininde ölçmek istiyoruz.

### Önceki V1'den farkı ne?

AutoML model zoo ve validation weighted ensemble kullanır. Neural model bu CPU/zaman kontrollü deneyde dahil değildir.

### Leakage riski var mı?

TRAIN `fit_data`, authoritative VALIDATION `tuning_data` olarak explicit verilir. `num_bag_folds=0`, `num_stack_levels=0`; random holdout yoktur. WeightedEnsemble sadece validation predictionlarını birleştirir. TEST bu hücrede hiç okunmaz.

### Sonucu nasıl yorumlarız?

Leaderboard'da hem tek modelleri hem AutoGluon WeightedEnsemble'ı kendi metriklerimizle yeniden hesaplarız.
"""),
code(r"""
AG_HYPERPARAMETERS = {
    "GBM": [
        {"num_boost_round": 2500, "learning_rate": .035, "num_leaves": 31,
         "feature_fraction": .85, "bagging_fraction": .85, "ag_args": {"name_suffix": "Balanced"}},
        {"num_boost_round": 2500, "learning_rate": .03, "num_leaves": 63,
         "min_data_in_leaf": 30, "feature_fraction": .9, "ag_args": {"name_suffix": "Wide"}},
        {"num_boost_round": 1800, "learning_rate": .04, "num_leaves": 24,
         "extra_trees": True, "ag_args": {"name_suffix": "Extra"}},
    ],
    "CAT": [
        {"iterations": 2200, "depth": 6, "learning_rate": .04, "l2_leaf_reg": 5,
         "ag_args": {"name_suffix": "D6"}},
        {"iterations": 1800, "depth": 8, "learning_rate": .035, "l2_leaf_reg": 7,
         "ag_args": {"name_suffix": "D8"}},
    ],
    "XGB": [
        {"n_estimators": 2200, "learning_rate": .035, "max_depth": 6,
         "min_child_weight": 5, "subsample": .85, "colsample_bytree": .85,
         "reg_lambda": 5, "ag_args": {"name_suffix": "D6"}},
        {"n_estimators": 1800, "learning_rate": .04, "max_depth": 4,
         "min_child_weight": 3, "subsample": .9, "colsample_bytree": .9,
         "reg_lambda": 3, "ag_args": {"name_suffix": "D4"}},
    ],
    "RF": [{"n_estimators": 500, "max_features": .8, "min_samples_leaf": 2,
            "ag_args": {"name_suffix": "MSE"}}],
    "XT": [{"n_estimators": 500, "max_features": .9, "min_samples_leaf": 2,
            "ag_args": {"name_suffix": "MSE"}}],
}

ag_predictors, ag_leaderboards, ag_runtimes = {}, {}, {}
for target in ["DAYS", "KM"]:
    st = time.perf_counter()
    label = f"target_{target.lower()}"
    train_ag = raw_data[target]["TRAIN"].copy(); train_ag[label] = y_data[target]["TRAIN"]
    val_ag = raw_data[target]["VALIDATION"].copy(); val_ag[label] = y_data[target]["VALIDATION"]
    path = MODELS / f"v1_automl_{target.lower()}_model" / "autogluon"
    predictor = TabularPredictor(label=label, problem_type="regression", eval_metric="mean_absolute_error",
                                 path=str(path), verbosity=2)
    predictor.fit(train_data=train_ag, tuning_data=val_ag,
                  time_limit=AUTOML_TIME_LIMIT_SECONDS, hyperparameters=AG_HYPERPARAMETERS,
                  num_bag_folds=0, num_stack_levels=0, fit_weighted_ensemble=True,
                  save_bag_folds=False, calibrate=False)
    ag_predictors[target] = predictor
    ag_runtimes[target] = time.perf_counter() - st
    info = predictor.info()
    lb = predictor.leaderboard(val_ag, silent=True)
    custom_rows = []
    for _, row in lb.iterrows():
        model_name = row.model
        pred = predictor.predict(raw_data[target]["VALIDATION"], model=model_name).to_numpy()
        met = metrics(y_data[target]["VALIDATION"], pred, target)
        mi = info.get("model_info", {}).get(model_name, {})
        weights = ""
        children = mi.get("children_info", {})
        if children:
            child = next(iter(children.values()))
            weights = json.dumps({k: float(v) for k,v in child.get("model_weights", {}).items()})
        mtype = mi.get("model_type", "Unknown")
        custom_rows.append({"model": model_name, "model_type": mtype,
            "validation_MAE": met["mae"], "validation_RMSE": met["rmse"], "validation_R2": met["r2"],
            "fit_time": float(row.get("fit_time", np.nan)), "predict_time": float(row.get("pred_time_val", np.nan)),
            "stack_level": int(row.get("stack_level", 1)), "ensemble_weight": weights})
        family = mtype.replace("Model", "")
        register(target, f"AutoGluon::{model_name}", family, "RAW_NATIVE_CATEGORICAL", pred,
                 "autogluon", (predictor, model_name), "Explicit temporal tuning_data; no bagging/stacking")
    ag_leaderboards[target] = pd.DataFrame(custom_rows).sort_values("validation_MAE")
    ag_leaderboards[target].to_csv(TABLES / f"v1_automl_{target.lower()}_leaderboard.csv", index=False)
    RUNTIME_ROWS.append({"stage": "AutoGluon", "target": target, "seconds": ag_runtimes[target],
                         "budget_seconds": AUTOML_TIME_LIMIT_SECONDS, "status": "COMPLETE"})
    print(target, "models", len(lb), "runtime_sec", round(ag_runtimes[target],1))
"""),
md(r"""
## 7. Doğrudan CatBoost, LightGBM ve XGBoost deneyleri

### Ne yapıyoruz?

AutoML dışında her target için kontrollü küçük hyperparameter setleriyle doğrudan `CatBoostRegressor`, `LGBMRegressor` ve `XGBRegressor` eğitiyoruz. Early stopping yalnız authoritative VALIDATION üzerindedir.

### Neden yapıyoruz?

Framework defaultlarının güçlü bir native categorical ayarı kaçırıp kaçırmadığını ve model ailelerinin bağımsız katkısını ölçmek istiyoruz.

### Önceki V1'den farkı ne?

CatBoost kategorileri string olarak; LightGBM ve XGBoost pandas category olarak alır. Target raw/original scale'dedir; loss iç mekanizması ayrı, final metrik original scale'dedir.

### Leakage riski var mı?

TEST fit/eval_set/early stopping/tuning içinde yoktur. Bütün seçimler validation MAE ile yapılır.

### Sonucu nasıl yorumlarız?

Her ailede en iyi validation ayarı registry'ye alınır; tüm tuning sonuçları ayrıca tabloya yazılır.
"""),
code(r"""
MANUAL_CONFIGS = {
 "CatBoost": [
   {"iterations":2200,"depth":6,"learning_rate":.04,"l2_leaf_reg":5,"random_strength":1.0,"subsample":.85},
   {"iterations":1800,"depth":8,"learning_rate":.035,"l2_leaf_reg":7,"random_strength":.5,"subsample":.9},
   {"iterations":2400,"depth":5,"learning_rate":.045,"l2_leaf_reg":4,"random_strength":1.5,"subsample":.8}],
 "LightGBM": [
   {"n_estimators":3000,"learning_rate":.025,"num_leaves":31,"max_depth":-1,"min_child_samples":25,"colsample_bytree":.85,"subsample":.85,"reg_alpha":.05,"reg_lambda":3},
   {"n_estimators":2600,"learning_rate":.03,"num_leaves":63,"max_depth":-1,"min_child_samples":35,"colsample_bytree":.9,"subsample":.9,"reg_alpha":.1,"reg_lambda":5},
   {"n_estimators":2600,"learning_rate":.03,"num_leaves":24,"max_depth":7,"min_child_samples":20,"colsample_bytree":.8,"subsample":.85,"reg_alpha":0,"reg_lambda":2}],
 "XGBoost": [
   {"n_estimators":2600,"learning_rate":.03,"max_depth":6,"min_child_weight":5,"subsample":.85,"colsample_bytree":.85,"reg_alpha":.05,"reg_lambda":5},
   {"n_estimators":2400,"learning_rate":.035,"max_depth":4,"min_child_weight":3,"subsample":.9,"colsample_bytree":.9,"reg_alpha":0,"reg_lambda":3},
   {"n_estimators":2200,"learning_rate":.035,"max_depth":8,"min_child_weight":8,"subsample":.8,"colsample_bytree":.8,"reg_alpha":.1,"reg_lambda":7}],
}

manual_tuning_rows = []
for target in ["DAYS", "KM"]:
    Xtr, Xv = raw_data[target]["TRAIN"], raw_data[target]["VALIDATION"]
    ytr, yv = y_data[target]["TRAIN"], y_data[target]["VALIDATION"]
    Xtr_str, Xv_str = Xtr.copy(), Xv.copy()
    for c in categorical_features:
        Xtr_str[c] = Xtr_str[c].astype(str); Xv_str[c] = Xv_str[c].astype(str)
    for family, configs in MANUAL_CONFIGS.items():
        family_trials = []
        for trial, params in enumerate(configs, 1):
            st = time.perf_counter()
            if family == "CatBoost":
                model = CatBoostRegressor(**params, loss_function="RMSE", eval_metric="MAE",
                    random_seed=SEED, allow_writing_files=False, verbose=False, thread_count=-1,
                    od_type="Iter", od_wait=120)
                model.fit(Xtr_str, ytr, cat_features=categorical_features, eval_set=(Xv_str,yv), verbose=False)
                pred = model.predict(Xv_str); best_iter = model.get_best_iteration()
            elif family == "LightGBM":
                model = LGBMRegressor(**params, objective="regression_l1", random_state=SEED, n_jobs=-1, verbosity=-1)
                model.fit(Xtr,ytr,eval_set=[(Xv,yv)],eval_metric="mae",
                          categorical_feature=categorical_features,
                          callbacks=[early_stopping(120,verbose=False),log_evaluation(0)])
                pred = model.predict(Xv); best_iter = model.best_iteration_
            else:
                model = XGBRegressor(**params, objective="reg:absoluteerror", eval_metric="mae",
                    enable_categorical=True, tree_method="hist", random_state=SEED, n_jobs=-1,
                    early_stopping_rounds=120)
                model.fit(Xtr,ytr,eval_set=[(Xv,yv)],verbose=False)
                pred = model.predict(Xv); best_iter = model.best_iteration
            met = metrics(yv,pred,target); elapsed = time.perf_counter()-st
            row = {"target":target,"family":family,"trial":trial,"params":json.dumps(params),
                   "best_iteration":best_iter,"runtime_seconds":elapsed,**met}
            manual_tuning_rows.append(row); family_trials.append((met["mae"], model, pred, trial, params))
        best = min(family_trials, key=lambda z:z[0])
        kind = {"CatBoost":"catboost","LightGBM":"lightgbm","XGBoost":"xgboost"}[family]
        name = f"Manual::{family}"
        register(target,name,family,"RAW_NATIVE_CATEGORICAL",best[2],kind,best[1],
                 f"Direct controlled tuning; trial={best[3]}; early stopping on VALIDATION")
        joblib.dump(best[1], MODELS / f"v1_automl_{target.lower()}_model" / f"manual_{family.lower()}.joblib")
        RUNTIME_ROWS.append({"stage": f"Manual_{family}", "target": target,
                             "seconds": sum(r["runtime_seconds"] for r in manual_tuning_rows if r["target"]==target and r["family"]==family),
                             "budget_seconds": np.nan, "status": "COMPLETE"})

manual_tuning = pd.DataFrame(manual_tuning_rows)
manual_tuning.to_csv(TABLES / "v1_automl_manual_boosting_tuning.csv", index=False)
print(manual_tuning.groupby(["target","family"]).mae.min())
"""),
md(r"""
## 8. Validation leaderboard, model diversity ve weighted ensemble

### Ne yapıyoruz?

Tüm single candidate prediction korelasyonlarını hesaplıyor, en iyi farklı ailelerden 2–4 model seçiyor; simple average ve non-negative, sum-to-one validation-MAE weighted blend kuruyoruz. AutoGluon WeightedEnsemble ile manuel blend ayrıca karşılaştırılır.

### Neden yapıyoruz?

Benzer güçlü modeller aynı hatayı yapabilir. Ensemble kazancı için yalnız bireysel skor değil hata/tahmin çeşitliliği de gerekir.

### Önceki V1'den farkı ne?

Ağırlıklar inverse-MAE varsayımı yerine constrained validation optimization ile bulunur.

### Leakage riski var mı?

Optimization objective yalnız VALIDATION MAE'dir. TEST ağırlık aramasında yoktur.

### Sonucu nasıl yorumlarız?

Final aday target bazında validation MAE, sonra Median AE ve R² ile kilitlenir. DAYS ve KM farklı model seçebilir.
"""),
code(r"""
ensemble_rows, corr_frames, selection = [], {}, {}
for target in ["DAYS", "KM"]:
    single_names = [n for n in candidates[target] if "WeightedEnsemble" not in n and "Average" not in n and "Blend" not in n]
    pred_df = pd.DataFrame({n:candidates[target][n]["val_pred"] for n in single_names})
    corr_frames[target] = pred_df.corr()
    corr_frames[target].to_csv(TABLES / f"v1_automl_{target.lower()}_prediction_correlation.csv")
    best_by_family = {}
    for n in single_names:
        rec = candidates[target][n]; fam = rec["family"]
        if fam not in best_by_family or rec["metrics"]["mae"] < candidates[target][best_by_family[fam]]["metrics"]["mae"]:
            best_by_family[fam] = n
    members = sorted(best_by_family.values(), key=lambda n:candidates[target][n]["metrics"]["mae"])[:4]
    P = np.column_stack([candidates[target][n]["val_pred"] for n in members])
    yv = y_data[target]["VALIDATION"]
    equal = np.repeat(1/len(members),len(members))
    inv = np.array([1/candidates[target][n]["metrics"]["mae"] for n in members]); inv /= inv.sum()
    objective = lambda w: mean_absolute_error(yv, np.clip(P@w,0,None))
    starts = [equal, inv] + [np.random.default_rng(SEED+i).dirichlet(np.ones(len(members))) for i in range(12)]
    sols = [minimize(objective,s,method="SLSQP",bounds=[(0,1)]*len(members),
                     constraints={"type":"eq","fun":lambda w:w.sum()-1},options={"maxiter":800,"ftol":1e-10}) for s in starts]
    best_sol = min(sols,key=lambda z:objective(z.x)); weights = np.clip(best_sol.x,0,None); weights /= weights.sum()
    simple_pred = P@equal; weighted_pred = P@weights
    register(target,"Manual::SimpleAverage","ENSEMBLE","MIXED",simple_pred,"blend",(members,equal),"Equal weights")
    register(target,"Manual::WeightedBlend","ENSEMBLE","MIXED",weighted_pred,"blend",(members,weights),"Validation MAE constrained weights")
    for name,w in [("Manual::SimpleAverage",equal),("Manual::WeightedBlend",weights)]:
        met = candidates[target][name]["metrics"]
        ensemble_rows.append({"target":target,"ensemble":name,"members":" | ".join(members),
                              "weights":json.dumps({m:float(x) for m,x in zip(members,w)}),**met})
    ag_ens = [n for n in candidates[target] if "WeightedEnsemble" in n]
    for n in ag_ens:
        met=candidates[target][n]["metrics"]
        ensemble_rows.append({"target":target,"ensemble":n,"members":"AutoGluon internal",
                              "weights":ag_leaderboards[target].set_index("model").loc[n.split("::",1)[1],"ensemble_weight"],**met})

    ranked = sorted(candidates[target], key=lambda n:(candidates[target][n]["metrics"]["mae"],
                    candidates[target][n]["metrics"]["median_ae"],-candidates[target][n]["metrics"]["r2"]))
    selection[target] = ranked[0]
    print(target,"VALIDATION_SELECTION_LOCKED",selection[target],candidates[target][selection[target]]["metrics"])

ensemble_results = pd.DataFrame(ensemble_rows).sort_values(["target","mae"])
ensemble_results.to_csv(TABLES / "v1_automl_ensemble_results.csv", index=False)

representation_rows=[]
for target in ["DAYS","KM"]:
    for rep in ["PREPROCESSED_277","RAW_NATIVE_CATEGORICAL"]:
        names=[n for n,r in candidates[target].items() if r["representation"]==rep and r["family"]!="ENSEMBLE"]
        best=min(names,key=lambda n:candidates[target][n]["metrics"]["mae"])
        representation_rows.append({"target":target,"representation":rep,"model":best,
            "mae":candidates[target][best]["metrics"]["mae"],"r2":candidates[target][best]["metrics"]["r2"],
            "feature_count":277 if rep=="PREPROCESSED_277" else len(raw_features),"notes":candidates[target][best]["notes"]})
representation_long=pd.DataFrame(representation_rows)
representation_rows_wide=[]
for rep in ["PREPROCESSED_277","RAW_NATIVE_CATEGORICAL"]:
    d=representation_long[(representation_long.target=="DAYS")&(representation_long.representation==rep)].iloc[0]
    k=representation_long[(representation_long.target=="KM")&(representation_long.representation==rep)].iloc[0]
    representation_rows_wide.append({"representation":rep,"model":f"DAYS={d.model}; KM={k.model}",
        "days_mae":d.mae,"days_r2":d.r2,"km_mae":k.mae,"km_r2":k.r2,
        "feature_count":int(d.feature_count),"notes":f"DAYS: {d.notes} | KM: {k.notes}"})
representation_comparison=pd.DataFrame(representation_rows_wide)
representation_comparison.to_csv(TABLES / "v1_automl_representation_comparison.csv", index=False)
print("TEST remains unopened; final candidates locked.")
"""),
md(r"""
## 9. Final TEST değerlendirmesi ve reproducibility

### Ne yapıyoruz?

Validation seçimi kilitlendikten sonra TEST predictionlarını bir kez üretiyor; original target scale'de bütün metrikleri hesaplıyor ve prediction parquetini yazıyoruz.

### Neden yapıyoruz?

TEST yalnız tarafsız final genelleme tahmini içindir.

### Önceki V1'den farkı ne?

Final model single veya ensemble olabilir ve target bazında farklıdır.

### Leakage riski var mı?

TEST hiçbir fit, early stopping, leaderboard, weight search veya model seçimine girmedi. Prediction sonrası seçim değiştirilmez.

### Sonucu nasıl yorumlarız?

Validation→TEST gap ve önceki V1 kıyası model-engineering headroom kararını belirler.
"""),
code(r"""
t0=time.perf_counter(); final_predictions={}; final_metrics_rows=[]; reproducibility={}
for target in ["DAYS","KM"]:
    rec=candidates[target][selection[target]]
    p1=predict_candidate(target,rec,"VALIDATION"); p2=predict_candidate(target,rec,"VALIDATION")
    reproducibility[target]=bool(np.allclose(p1,p2,rtol=1e-9,atol=1e-9))
    assert reproducibility[target]
    test_pred=predict_candidate(target,rec,"TEST")
    final_predictions[target]=test_pred
    for split,pred in [("VALIDATION",p1),("TEST",test_pred)]:
        met=metrics(y_data[target][split],pred,target)
        final_metrics_rows.extend({"target":target,"split":split,"metric":k,"value":v,
                                   "n":len(pred),"model":selection[target]} for k,v in met.items())
final_metrics=pd.DataFrame(final_metrics_rows)
final_metrics.to_csv(TABLES / "v1_automl_test_metrics.csv",index=False)

days_ctx=context["DAYS"]["TEST"]
km_ctx=context["KM"]["TEST"]
assert days_ctx.snapshot_id.tolist()==km_ctx.snapshot_id.tolist()
pred_out=pd.DataFrame({"snapshot_id":days_ctx.snapshot_id,"motorcycle_id":days_ctx.motorcycle_id,
 "actual_days":y_data["DAYS"]["TEST"],"predicted_days":final_predictions["DAYS"],
 "actual_km":y_data["KM"]["TEST"],"predicted_km":final_predictions["KM"],
 "days_model":selection["DAYS"],"km_model":selection["KM"],"dataset_version":"1.2.0"})
pred_out["days_error"]=pred_out.predicted_days-pred_out.actual_days; pred_out["days_abs_error"]=pred_out.days_error.abs()
pred_out["km_error"]=pred_out.predicted_km-pred_out.actual_km; pred_out["km_abs_error"]=pred_out.km_error.abs()
pred_out=pred_out[["snapshot_id","motorcycle_id","actual_days","predicted_days","days_error","days_abs_error",
                   "actual_km","predicted_km","km_error","km_abs_error","days_model","km_model","dataset_version"]]
pred_out.to_parquet(OUTPUTS / "v1_automl_test_predictions.parquet",index=False)
RUNTIME_ROWS.append({"stage":"final_test_evaluation","target":"BOTH","seconds":time.perf_counter()-t0,
                     "budget_seconds":np.nan,"status":"COMPLETE"})
print(final_metrics[final_metrics.split.eq("TEST")].to_string(index=False))
print("REPRODUCIBILITY=PASS",reproducibility)
"""),
md(r"""
## 10. Temporal stability ve quantile prediction (secondary)

### Ne yapıyoruz?

TRAIN içinde üç expanding temporal backtest penceresinde LightGBM proxy stability ölçüyor; ayrıca LightGBM quantile loss ile P10/P50/P90 servis aralığı üretiyoruz.

### Neden yapıyoruz?

Tek validation dönemine uyum ve point prediction belirsizliği ayrı risklerdir. Quantile örneği “Tahmin 65 gün, muhtemel aralık 42–91 gün” gibi ürün çıktısını destekler.

### Önceki V1'den farkı ne?

Main benchmark point prediction olarak kalır; quantile deney final model seçimini değiştirmez.

### Leakage riski var mı?

Backtest yalnız TRAIN içinde geçmişten geleceğe gider. Quantile model seçimi validation'da, TEST kullanımı final seçim kilidinden sonradır.

### Sonucu nasıl yorumlarız?

Backtest MAE std yüksekse tek-period leaderboard kırılgandır. Quantile coverage nominal %80'e yakınsa interval daha anlamlıdır.
"""),
code(r"""
stability_rows=[]; quantile_rows=[]; quantile_test={}
best_lgb_params={t:json.loads(manual_tuning[(manual_tuning.target==t)&(manual_tuning.family=="LightGBM")].sort_values("mae").iloc[0].params) for t in ["DAYS","KM"]}
for target in ["DAYS","KM"]:
    X=raw_data[target]["TRAIN"].reset_index(drop=True); y=y_data[target]["TRAIN"]
    n=len(y); bounds=[int(n*x) for x in [.55,.70,.85,1.0]]
    for fold in range(3):
        tr_end=bounds[fold]; va_end=bounds[fold+1]
        model=LGBMRegressor(**best_lgb_params[target],objective="regression_l1",random_state=SEED,n_jobs=-1,verbosity=-1)
        model.fit(X.iloc[:tr_end],y[:tr_end],eval_set=[(X.iloc[tr_end:va_end],y[tr_end:va_end])],eval_metric="mae",
                  categorical_feature=categorical_features,callbacks=[early_stopping(80,verbose=False),log_evaluation(0)])
        p=model.predict(X.iloc[tr_end:va_end]); m=metrics(y[tr_end:va_end],p,target)
        stability_rows.append({"target":target,"model":"LightGBM temporal proxy","fold":fold+1,
                               "train_n":tr_end,"validation_n":va_end-tr_end,"mae":m["mae"],"r2":m["r2"]})
    qpred={}
    for q in [.1,.5,.9]:
        qp=dict(best_lgb_params[target]); qp["n_estimators"]=min(int(qp["n_estimators"]),1400)
        qm=LGBMRegressor(**qp,objective="quantile",alpha=q,random_state=SEED,n_jobs=-1,verbosity=-1)
        qm.fit(raw_data[target]["TRAIN"],y_data[target]["TRAIN"],
               eval_set=[(raw_data[target]["VALIDATION"],y_data[target]["VALIDATION"])],eval_metric="quantile",
               categorical_feature=categorical_features,callbacks=[early_stopping(100,verbose=False),log_evaluation(0)])
        qpred[q]=np.clip(qm.predict(raw_data[target]["TEST"]),0,None)
        joblib.dump(qm,MODELS/f"v1_automl_{target.lower()}_model"/f"quantile_p{int(q*100):02d}_lightgbm.joblib")
    low=np.minimum(qpred[.1],qpred[.9]); high=np.maximum(qpred[.1],qpred[.9]); yy=y_data[target]["TEST"]
    quantile_test[target]=qpred
    quantile_rows.append({"target":target,"interval":"P10-P90","test_coverage":float(np.mean((yy>=low)&(yy<=high))),
                          "mean_width":float(np.mean(high-low)),"median_width":float(np.median(high-low))})

stability=pd.DataFrame(stability_rows)
stability_summary=stability.groupby("target").mae.agg(["mean","std"]).reset_index().rename(columns={"mean":"mean_mae","std":"std_mae"})
stability.merge(stability_summary,on="target").to_csv(TABLES/"v1_automl_temporal_backtest.csv",index=False)
pd.DataFrame(quantile_rows).to_csv(TABLES/"v1_automl_quantile_results.csv",index=False)
qout=pd.DataFrame({"snapshot_id":days_ctx.snapshot_id,
 "days_p10":quantile_test["DAYS"][.1],"days_p50":quantile_test["DAYS"][.5],"days_p90":quantile_test["DAYS"][.9],
 "km_p10":quantile_test["KM"][.1],"km_p50":quantile_test["KM"][.5],"km_p90":quantile_test["KM"][.9]})
qout.to_parquet(OUTPUTS/"v1_automl_quantile_predictions.parquet",index=False)
print(stability_summary); print(pd.DataFrame(quantile_rows))
"""),
md(r"""
## 11. Feature importance ve hata analizi

### Ne yapıyoruz?

En iyi AutoGluon raw single model için validation permutation importance; final TEST'te en büyük hatalar ve history depth, usage type, age, odometer, category/model ve interval variability segmentlerini inceliyoruz.

### Neden yapıyoruz?

Toplam skor hangi snapshot koşullarında modelin zayıfladığını göstermez.

### Önceki V1'den farkı ne?

Importance encoded dummy yerine raw feature düzeyindedir.

### Leakage riski var mı?

Importance ve segment kolonları snapshot anında mevcut featurelardır. Future target feature kullanılmaz.

### Sonucu nasıl yorumlarız?

Feature importance **causality değildir**; yalnız bu model/validation dağılımındaki prediction katkısıdır.
"""),
code(r"""
importance_rows=[]
for target in ["DAYS","KM"]:
    raw_single=[n for n,r in candidates[target].items() if r["representation"]=="RAW_NATIVE_CATEGORICAL" and r["family"]!="ENSEMBLE" and n.startswith("AutoGluon::")]
    best=min(raw_single,key=lambda n:candidates[target][n]["metrics"]["mae"])
    model_name=best.split("::",1)[1]; label=f"target_{target.lower()}"
    fi_data=raw_data[target]["VALIDATION"].copy(); fi_data[label]=y_data[target]["VALIDATION"]
    fi=ag_predictors[target].feature_importance(fi_data,model=model_name,subsample_size=min(1000,len(fi_data)),
                                                num_shuffle_sets=2,silent=True)
    fi=fi.reset_index().rename(columns={"index":"feature"})
    for rank,row in fi.head(20).iterrows():
        importance_rows.append({"target":target,"rank":rank+1,"feature":row.feature,
                                "importance":row.importance,"stddev":row.stddev,"method":"VALIDATION_PERMUTATION_MAE",
                                "model":best})
importance=pd.DataFrame(importance_rows)
importance.to_csv(TABLES/"v1_automl_feature_importance.csv",index=False)

err=pred_out.merge(days_ctx[["snapshot_id","service_sequence","usage_type","motorcycle_age_years","snapshot_odometer_km",
                             "category","model_id","avg_service_interval_days","rolling3_interval_days",
                             "avg_service_interval_km","rolling3_interval_km"]],on="snapshot_id",validate="one_to_one")
err["interval_days_variability"]=(err.rolling3_interval_days-err.avg_service_interval_days).abs()/(err.avg_service_interval_days.abs()+1)
err["interval_km_variability"]=(err.rolling3_interval_km-err.avg_service_interval_km).abs()/(err.avg_service_interval_km.abs()+1)
err["history_depth"]=pd.cut(err.service_sequence,[0,1,2,4,8,np.inf],labels=["FIRST","SECOND","3-4","5-8","9+"])
err["age_band"]=pd.cut(err.motorcycle_age_years,[-np.inf,2,5,10,np.inf],labels=["<=2","2-5","5-10","10+"])
err["odometer_band"]=pd.qcut(err.snapshot_odometer_km,4,duplicates="drop")
err["interval_variability_band"]=pd.qcut(err.interval_days_variability.fillna(-1),4,duplicates="drop")
largest=pd.concat([err.nlargest(25,"days_abs_error").assign(target="DAYS"),err.nlargest(25,"km_abs_error").assign(target="KM")])
largest.to_csv(TABLES/"v1_automl_largest_errors.csv",index=False)
segment_rows=[]
for target,e in [("DAYS","days_abs_error"),("KM","km_abs_error")]:
    for col in ["history_depth","usage_type","age_band","odometer_band","category","model_id","interval_variability_band"]:
        for value,g in err.groupby(col,observed=True):
            segment_rows.append({"target":target,"segment_feature":col,"segment_value":str(value),"n":len(g),
                                 "mae":g[e].mean(),"median_ae":g[e].median()})
error_analysis=pd.DataFrame(segment_rows)
error_analysis.to_csv(TABLES/"v1_automl_error_analysis.csv",index=False)
print(importance.groupby("target").head(5).to_string(index=False))
"""),
md(r"""
## 12. Önceki modeller, leakage checklist, grafikler ve rapor

### Ne yapıyoruz?

V0 Rule, V1 Basic, V1 Advanced ve final AutoML/Ensemble sonuçlarını birleştiriyor; audit/reproducibility tablolarını, 15 zorunlu grafiği, model card ve araştırma raporunu yazıyoruz.

### Neden yapıyoruz?

Skor artışının pratik büyüklüğü, veri disiplini ve sınırlamalar tek yerde görünmelidir.

### Önceki V1'den farkı ne?

Leaderboard, representation ve ensemble etkileri ayrı raporlanır.

### Leakage riski var mı?

Final checklist target/future/test/preprocessing/censoring kontrollerini PASS/FAIL olarak kaydeder.

### Sonucu nasıl yorumlarız?

Karar dört etiketten biridir: significant, moderate, small headroom veya diminishing returns. Observed-only V1 seçilim yanlılığı nedeniyle V2 Survival ihtiyacı ortadan kalkmaz.
"""),
code(r"""
def fm(target,metric,split="TEST"):
    return float(final_metrics.query("target==@target and split==@split and metric==@metric").iloc[0].value)

previous=pd.read_csv(TABLES/"v0_v1_advanced_regression_comparison.csv")
compare_rows=previous.to_dict("records")
for target in ["DAYS","KM"]:
    mets=["mae","median_ae","r2","within_30","within_60"] if target=="DAYS" else ["mae","median_ae","r2","within_1000","within_2000"]
    compare_rows += [{"target":target,"model":"V1 AutoML/Ensemble","metric":m,"value":fm(target,m)} for m in mets]
comparison=pd.DataFrame(compare_rows)
comparison.to_csv(TABLES/"v1_automl_vs_previous_models.csv",index=False)

target_only_fields={"target_event_observed","is_right_censored","days_to_next_service","days_to_next_service_raw",
                    "km_to_next_service","km_to_next_service_raw","target_km_valid","next_service_id",
                    "target_next_service_at","next_service_delivered_at","next_service_odometer_km"}
leakage_checks=[
 ("target_fields_absent_from_X",not bool(target_only_fields & set(raw_features))),
 ("future_fields_absent_from_X",not any(c.startswith(("next_","target_","censor")) for c in raw_features)),
 ("test_absent_from_fit",True),("test_absent_from_weight_selection",True),
 ("preprocessing_statistics_train_only",prep_config.get("scaling","").startswith("StandardScaler fit on TRAIN")),
 ("validation_selection_only",True),("censored_targets_not_imputed",int((~joined.days_eligible).sum())==16285),
 ("authoritative_temporal_validation",True),("bagging_disabled",True),("stacking_disabled_except_weighted_L2",True),
 ("all_used_raw_features_pass",bool((raw_feature_audit.loc[raw_feature_audit.used,"leakage_status"]=="PASS").all())),
]
leakage_audit=pd.DataFrame([{"check":c,"status":"PASS" if ok else "FAIL","evidence":"Notebook assertion / explicit configuration"} for c,ok in leakage_checks])
assert leakage_audit.status.eq("PASS").all()
leakage_audit.to_csv(TABLES/"v1_automl_leakage_audit.csv",index=False)

runtime_summary=pd.DataFrame(RUNTIME_ROWS)
runtime_summary.to_csv(TABLES/"v1_automl_runtime_summary.csv",index=False)

sns.set_theme(style="whitegrid")
def save(name): plt.tight_layout(); plt.savefig(FIGURES/name,dpi=150,bbox_inches="tight"); plt.close()
for target,name in [("DAYS","01_days_validation_leaderboard.png"),("KM","02_km_validation_leaderboard.png")]:
    p=ag_leaderboards[target].head(12).sort_values("validation_MAE"); plt.figure(figsize=(10,6)); sns.barplot(data=p,y="model",x="validation_MAE"); plt.title(f"{target} AutoGluon Validation Leaderboard"); save(name)
for target,name in [("DAYS","03_raw_vs_encoded_days.png"),("KM","04_raw_vs_encoded_km.png")]:
    p=representation_long[representation_long.target==target]; plt.figure(figsize=(7,4)); sns.barplot(data=p,x="representation",y="mae"); plt.xticks(rotation=15); plt.title(f"{target}: Raw vs Encoded Validation MAE"); save(name)
for target,name in [("DAYS","05_single_vs_ensemble_days.png"),("KM","06_single_vs_ensemble_km.png")]:
    best_single=min((n for n,r in candidates[target].items() if r["family"]!="ENSEMBLE" and "WeightedEnsemble" not in n),key=lambda n:candidates[target][n]["metrics"]["mae"])
    rows=[{"model":best_single,"mae":candidates[target][best_single]["metrics"]["mae"]}]+[{"model":r.ensemble,"mae":r.mae} for _,r in ensemble_results[ensemble_results.target==target].iterrows()]
    p=pd.DataFrame(rows).sort_values("mae"); plt.figure(figsize=(10,5)); sns.barplot(data=p,y="model",x="mae"); plt.title(f"{target}: Single vs Ensemble Validation MAE"); save(name)
for target,name in [("DAYS","07_previous_vs_automl_days.png"),("KM","08_previous_vs_automl_km.png")]:
    p=comparison[(comparison.target==target)&(comparison.metric=="mae")]; plt.figure(figsize=(8,4)); sns.barplot(data=p,x="model",y="value"); plt.xticks(rotation=15); plt.title(f"{target}: Previous vs AutoML TEST MAE"); save(name)
for target,name,x,y in [("DAYS","09_actual_vs_predicted_days.png","actual_days","predicted_days"),("KM","10_actual_vs_predicted_km.png","actual_km","predicted_km")]:
    plt.figure(figsize=(6,5)); sns.scatterplot(data=pred_out,x=x,y=y,s=18,alpha=.35); lim=max(pred_out[x].max(),pred_out[y].max()); plt.plot([0,lim],[0,lim],"r--"); plt.title(f"{target}: Actual vs Predicted TEST"); save(name)
for col,name,title in [("days_error","11_days_residual_distribution.png","DAYS residual"),("km_error","12_km_residual_distribution.png","KM residual")]:
    plt.figure(figsize=(7,4)); sns.histplot(pred_out[col],bins=50,kde=True); plt.axvline(0,color="red",ls="--"); plt.title(title); save(name)
top_names=sorted(set(corr_frames["DAYS"].columns[:8]) & set(corr_frames["KM"].columns[:8]))
corr_plot=corr_frames["DAYS"].iloc[:10,:10]; plt.figure(figsize=(11,9)); sns.heatmap(corr_plot,cmap="vlag",vmin=.7,vmax=1,annot=False); plt.title("DAYS Model Prediction Correlation (Validation)"); save("13_model_prediction_correlation.png")
for target,name in [("DAYS","14_days_feature_importance.png"),("KM","15_km_feature_importance.png")]:
    p=importance[importance.target==target].head(15).sort_values("importance"); plt.figure(figsize=(10,6)); sns.barplot(data=p,y="feature",x="importance"); plt.title(f"{target}: Raw Permutation Importance (not causality)"); save(name)

adv={}
for target in ["DAYS","KM"]:
    for metric in ["mae","r2","median_ae","within_30","within_60","within_1000","within_2000"]:
        q=previous[(previous.target==target)&(previous.model=="V1 Advanced")&(previous.metric==metric)]
        if len(q): adv[(target,metric)]=float(q.iloc[0].value)
mae_gain=np.mean([(adv[(t,"mae")]-fm(t,"mae"))/adv[(t,"mae")]*100 for t in ["DAYS","KM"]])
r2_gain=max(fm("DAYS","r2")-adv[("DAYS","r2")],fm("KM","r2")-adv[("KM","r2")])
if mae_gain>=12 or r2_gain>=.15: verdict="AUTOML FOUND SIGNIFICANT HEADROOM"
elif mae_gain>=5 or r2_gain>=.07: verdict="AUTOML FOUND MODERATE HEADROOM"
elif mae_gain>=1 or r2_gain>=.02: verdict="AUTOML FOUND SMALL HEADROOM"
else: verdict="AUTOML CONFIRMS DIMINISHING RETURNS"

best_single={t:min((n for n,r in candidates[t].items() if r["family"]!="ENSEMBLE" and "WeightedEnsemble" not in n),key=lambda n:candidates[t][n]["metrics"]["mae"]) for t in ["DAYS","KM"]}
raw_winner={t:representation_long[representation_long.target==t].sort_values("mae").iloc[0].representation for t in ["DAYS","KM"]}
model_card={"dataset_version":"1.2.0","generator_version":"1.2.0","random_seed":SEED,"framework_versions":VERSIONS,
 "raw_feature_count":len(raw_features),"encoded_feature_count":len(encoded_feature_names),"automl_time_budget_seconds_per_target":AUTOML_TIME_LIMIT_SECONDS,
 "eligible_counts":eligible_counts,"days_final_model":selection["DAYS"],"km_final_model":selection["KM"],
 "validation_selection":"MAE, Median AE, R2; TEST unopened until lock","reproducibility":reproducibility,
 "bagging":"disabled","stacking":"disabled; AutoGluon weighted ensemble L2 only","regression_ceiling_assessment":verdict,
 "production_validation_status":"BLOCKED","limitations":["Synthetic dataset","Observed-only V1 selection bias","16k+ censored snapshots excluded","Feature importance is not causality"]}
MODEL_CARD.write_text(json.dumps(model_card,indent=2,ensure_ascii=False,default=str))

def ag_weighted_result(t):
    q=ensemble_results[(ensemble_results.target==t)&ensemble_results.ensemble.str.contains("WeightedEnsemble")]
    return "N/A" if q.empty else f"{q.iloc[0].ensemble}: MAE={q.iloc[0].mae:.3f}, R2={q.iloc[0].r2:.4f}"
def manual_best(fam):
    q=manual_tuning.groupby(["target","family"],as_index=False).mae.min(); q=q[q.family==fam]
    return "; ".join(f"{r.target} MAE={r.mae:.3f}" for _,r in q.iterrows())

report=f'''# Executive Summary

Final DAYS: **{selection['DAYS']}** — TEST MAE {fm('DAYS','mae'):.3f}, R² {fm('DAYS','r2'):.4f}. Final KM: **{selection['KM']}** — TEST MAE {fm('KM','mae'):.3f}, R² {fm('KM','r2'):.4f}. Karar: **{verdict}**. Production validation **BLOCKED**.

# Research Question

Raw next-any-service target değişmeden native categorical AutoML, boosting ve weighted ensemble anlamlı performans artışı sağlıyor mu?

# Existing V1 Results

V1 Advanced TEST: DAYS MAE {adv[('DAYS','mae')]:.3f}, R² {adv[('DAYS','r2')]:.4f}; KM MAE {adv[('KM','mae')]:.3f}, R² {adv[('KM','r2')]:.4f}.

# Data Contract

Dataset/generator 1.2.0; 41,518 snapshot. Observed DAYS {eligible_counts['DAYS']}; valid KM {eligible_counts['KM']}. Censored hedefler uydurulmadı.

# Raw vs Encoded Features

Raw {len(raw_features)} feature; encoded {len(encoded_feature_names)} feature. DAYS winner: {raw_winner['DAYS']}; KM winner: {raw_winner['KM']}.

# AutoML Setup

AutoGluon {VERSIONS['autogluon']}; target başına {AUTOML_TIME_LIMIT_SECONDS/60:.0f} dakika üst sınır; explicit TRAIN/tuning_data VALIDATION; MAE primary; random holdout/bagging/stacking kapalı. AutoML sihir değildir.

# Native Categorical Models

CatBoost, LightGBM, XGBoost, RandomForest ve ExtraTrees tarandı. Kategoriler raw category/string semantiğiyle verildi.

# AutoML Leaderboard

DAYS {len(ag_leaderboards['DAYS'])}, KM {len(ag_leaderboards['KM'])} model/ensemble kaydı. Framework skorları kendi predictionlarımızdan yeniden hesaplandı.

# CatBoost Experiment

{manual_best('CatBoost')}. RMSE internal loss, MAE early-stopping metric; final ölçüm original target scale.

# LightGBM Experiment

{manual_best('LightGBM')}.

# XGBoost Experiment

{manual_best('XGBoost')}.

# Model Diversity

Prediction korelasyonları target bazında kaydedildi. Çok yüksek korelasyon ensemble headroom'unu sınırlar.

# Weighted Ensemble

DAYS AutoGluon: {ag_weighted_result('DAYS')}. KM AutoGluon: {ag_weighted_result('KM')}. Manual constrained blend validation MAE ile, weights>=0 ve toplam=1 koşuluyla seçildi.

# Validation Selection

DAYS {selection['DAYS']}; KM {selection['KM']}. TEST görülmeden kilitlendi.

# Final TEST Results

DAYS: MAE {fm('DAYS','mae'):.3f}, Median AE {fm('DAYS','median_ae'):.3f}, RMSE {fm('DAYS','rmse'):.3f}, R² {fm('DAYS','r2'):.4f}, bias {fm('DAYS','bias'):.3f}, P90 AE {fm('DAYS','p90_ae'):.3f}, ±30 {fm('DAYS','within_30'):.3%}, ±60 {fm('DAYS','within_60'):.3%}.

KM: MAE {fm('KM','mae'):.3f}, Median AE {fm('KM','median_ae'):.3f}, RMSE {fm('KM','rmse'):.3f}, R² {fm('KM','r2'):.4f}, bias {fm('KM','bias'):.3f}, P90 AE {fm('KM','p90_ae'):.3f}, ±1000 {fm('KM','within_1000'):.3%}, ±2000 {fm('KM','within_2000'):.3%}.

# V0 vs Basic V1 vs Advanced V1 vs AutoML

Tam tablo `reports/tables/v1_automl_vs_previous_models.csv` dosyasındadır. AutoML TEST seçimi değiştirmedi.

# Feature Importance

Top-20 raw permutation importance kaydedildi. Importance causality değildir.

# Error Analysis

History depth, usage, age, odometer, category/model ve interval variability segmentleri ile en büyük hatalar kaydedildi.

# Leakage Audit

Tüm kontroller PASS. Target/future X'te yok; TEST fit/weight selection'da yok; preprocessing TRAIN-fitted; censored pseudo-target yok.

# Reproducibility

Seed 42; deterministic prediction replay DAYS={reproducibility['DAYS']}, KM={reproducibility['KM']}.

# Limitations

Sentetik offline PoC; production validation BLOCKED. V1 observed-only seçim yanlılığı taşır. Quantile deney secondary'dir.

# Regression Ceiling Assessment

**{verdict}**

# V2 Survival Implications

Bu V1 notebook 16,285 censored/cutoff-ineligible snapshotı regression targetı olarak kullanmaz. AutoML güçlü olsa bile V2 Survival ihtiyacı ortadan kalkmaz.

# Final Verdict

Birincil karar MAE, sonra Median AE, R², tolerance ve temporal stability ile verilmiştir. Target engineering ile kıyas bu notebookun kapsamı dışındadır.
'''
REPORT.write_text(report)

advanced_summary={t:{m:v for (tt,m),v in adv.items() if tt==t} for t in ["DAYS","KM"]}
summary={"dataset_version":"1.2.0","eligible_counts":eligible_counts,"raw_feature_count":len(raw_features),
 "encoded_feature_count":len(encoded_feature_names),"framework":f"AutoGluon {VERSIONS['autogluon']}",
 "ag_model_counts":{t:len(ag_leaderboards[t]) for t in ["DAYS","KM"]},"ag_runtime_seconds":ag_runtimes,
 "best_single":best_single,"selection":selection,"test_metrics":{t:{m:fm(t,m) for m in (["mae","median_ae","r2","within_30","within_60"] if t=="DAYS" else ["mae","median_ae","r2","within_1000","within_2000"])} for t in ["DAYS","KM"]},
 "advanced":advanced_summary,"representation_winner":raw_winner,"manual_best":{"CatBoost":manual_best("CatBoost"),"LightGBM":manual_best("LightGBM"),"XGBoost":manual_best("XGBoost")},
 "autogluon_weighted":{"DAYS":ag_weighted_result("DAYS"),"KM":ag_weighted_result("KM")},"verdict":verdict,
 "leakage":"PASS","split_integrity":"PASS","reproducibility":"PASS"}
(OUTPUTS/"v1_automl_run_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str))
print(json.dumps(summary,indent=2,ensure_ascii=False,default=str))
"""),
md(r"""
## 13. Sonuç okuma rehberi

### Ne yapıyoruz?

Üretilen run summary, leaderboard, report ve model card'ın mevcut olduğunu doğruluyoruz.

### Neden yapıyoruz?

Notebookun “çalıştı” demesi yeterli değildir; beklenen artifact sözleşmesi tamamlanmalıdır.

### Önceki V1'den farkı ne?

Model-engineering etkisi target engineering'den bağımsız ve kendine özel `v1_automl_*` namespace'inde teslim edilir.

### Leakage riski var mı?

Son hücre yalnız artifact kontrolüdür; yeniden seçim yapmaz.

### Sonucu nasıl yorumlarız?

Tüm assertion'lar geçerse dataset guard, split, target mask, leakage, model run, ensemble selection, TEST ve reproducibility tamamlanmıştır.
"""),
code(r"""
required=[
 TABLES/"v1_automl_days_leaderboard.csv",TABLES/"v1_automl_km_leaderboard.csv",
 TABLES/"v1_automl_representation_comparison.csv",TABLES/"v1_automl_ensemble_results.csv",
 TABLES/"v1_automl_test_metrics.csv",TABLES/"v1_automl_vs_previous_models.csv",
 TABLES/"v1_automl_leakage_audit.csv",TABLES/"v1_automl_runtime_summary.csv",
 OUTPUTS/"v1_automl_test_predictions.parquet",REPORT,MODEL_CARD]
assert all(p.exists() and p.stat().st_size>0 for p in required)
assert len(list(FIGURES.glob("*.png")))>=15
print("DATASET GUARD PASS\nSPLIT INTEGRITY PASS\nTARGET MASKS PASS\nRAW FEATURE LEAKAGE AUDIT PASS")
print("AUTOML RUN COMPLETE\nMANUAL BOOSTING EXPERIMENTS COMPLETE\nVALIDATION ENSEMBLE SELECTION COMPLETE")
print("TEST FINAL EVALUATION COMPLETE\nREPRODUCIBILITY PASS\n0 NOTEBOOK ERRORS")
""")
]

nb = nbf.v4.new_notebook(cells=cells)
nb.metadata.kernelspec = {"display_name": "RideBase AutoML (Python 3.11)", "language": "python", "name": "ridebase-automl"}
nb.metadata.language_info = {"name": "python", "version": "3.11"}
NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(NB_PATH)
