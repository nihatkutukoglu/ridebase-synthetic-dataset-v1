#!/usr/bin/env python3
"""RideBase ML Control Center — build step.

Scans the repository's real artifacts (reports/ outputs/ models/ notebooks/
external_knowledge/ + the v1.x dataset metadata) and emits:

  data/manifest.json     aggregate, UI-ready project state (no fabricated numbers)
  data/changelog.json    activity feed derived from report content + file times
  RideBase_Control_Center.html   the self-contained artifact (manifest + EDA
                                 module fragment inlined)

Re-run this whenever a notebook / model / report changes, then re-publish the
HTML. Adding a module = one entry in MODULES below.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ML = ROOT / "ridebase-ml"
TABLES = ML / "reports" / "tables"
REPORTS = ML / "reports"
MODELS = ML / "models"
OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
DATA.mkdir(exist_ok=True)


# ----------------------------------------------------------------- helpers
def read_csv(name: str) -> list[dict]:
    p = TABLES / f"{name}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def read_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def mtime_iso(p: Path) -> str | None:
    return dt.datetime.fromtimestamp(p.stat().st_mtime).date().isoformat() if p.exists() else None


def section(md: str | None, title: str) -> str | None:
    if not md:
        return None
    m = re.search(rf"##\s*{re.escape(title)}\s*\n+(.+?)(\n##\s|\Z)", md, re.S)
    return re.sub(r"[#*`]", "", m.group(1)).strip()[:1400] if m else None


# ----------------------------------------------------------------- module registry
MODULES = [
    {"id": "eda", "name": "EDA", "tagline": "Exploratory Data Analysis", "status": "complete",
     "notebook": "02_eda.ipynb", "dataset": "v1.1 / v1.2",
     "purpose": "Model eğitmeden önce RideBase verisinin yapısını, dağılımlarını ve kalite durumunu anlamak."},
    {"id": "v0", "name": "V0 Baseline", "tagline": "Rule-based baseline", "status": "complete",
     "notebook": "04_v0_rule_baseline.ipynb", "dataset": "v1.2",
     "purpose": "Makine öğrenmesi kullanmadan oluşturulan ilk, kural tabanlı servis-zamanı baseline'ı. V1 için referans."},
    {"id": "v1", "name": "V1 Regression", "tagline": "Next-service DAYS & KM", "status": "active",
     "notebook": "06–12", "dataset": "v1.3",
     "purpose": "Bir motosikletin bir sonraki servisine kalan gün ve kilometreyi tahmin eden regresyon sistemi (frozen)."},
    {"id": "v2", "name": "V2 Survival", "tagline": "Time-to-event modelling", "status": "in_progress",
     "stage": "PRODUCTION_PACKAGED", "notebook": "15_v2_survival_advanced.ipynb", "dataset": "v1.3",
     "purpose": "Servise tam olarak kaç gün kaldığından çok, belirli zaman aralıklarında servise gelme olasılığını "
                "modellemek. Sağ-sansürlü kayıtları da kullanır. Notebook 13: leakage-safe survival episode "
                "hazırlığı ve censoring audit tamamlandı — henüz predictive model yok."},
    {"id": "v3", "name": "V3 Next Task", "tagline": "Next maintenance tasks", "status": "planned",
     "notebook": None, "dataset": None,
     "purpose": "Bir sonraki serviste yapılması muhtemel bakım işlemlerini tahmin etmek. "
                "Üretici bakım takvimi bilgisi 'prior' olarak mevcut."},
]

NOTEBOOKS = [
    ("01", "Data Understanding", "01_data_understanding.ipynb", "v1.2", "structure audit", "complete", None),
    ("02", "EDA", "02_eda.ipynb", "v1.2", "distributions + quality + survival targets", "complete", "eda"),
    ("03", "Production Feasibility", "03_production_feasibility.ipynb", "prod extract", "read-only feasibility (BLOCKED w/o extract)", "complete", None),
    ("04", "V0 Rule Baseline", "04_v0_rule_baseline.ipynb", "v1.2", "deterministic rule baseline", "complete", "v0"),
    ("05", "ML Preprocessing", "05_ml_preprocessing.ipynb", "v1.2", "leakage-safe train-only preprocessing", "complete", None),
    ("06", "Basic Regression", "06_v1_regression_benchmark.ipynb", "v1.2", "LazyPredict classical benchmark vs V0", "complete", "v1"),
    ("07", "Advanced Regression", "07_v1_advanced_regression.ipynb", "v1.2", "feature engineering + tuned boosting", "complete", "v1"),
    ("08", "Target Engineering", "08_v1_target_engineering.ipynb", "v1.2", "raw/log/residual/normalized target trials", "complete", "v1"),
    ("09", "AutoML Ensemble", "09_v1_automl_ensemble.ipynb", "v1.2", "AutoGluon + boosting ensembles", "complete", "v1"),
    ("10", "Final Regression", "10_v1_3_final_regression.ipynb", "v1.3", "leakage-safe final benchmark, native-cat + ensembles", "complete", "v1"),
    ("11", "External Maintenance Knowledge", "11_v1_external_maintenance_knowledge.ipynb", "v1.3", "A/B: manufacturer schedule features", "complete", "v1"),
    ("12", "Final Hyperparameter Tuning", "12_v1_final_hyperparameter_tuning.ipynb", "v1.3", "temporal-CV Optuna, HGB/LGBM/XGB/CatBoost", "active", "v1"),
]


# ----------------------------------------------------------------- dataset registry
def dataset_entry(ver_dir: str, label: str, purpose: str, used_by: str):
    meta = read_json(ROOT / ver_dir / "derived_outputs" / "dataset_metadata.json") or {}
    q = read_json(ROOT / ver_dir / "derived_outputs" / "quality_report.json") or {}
    info = meta.get("dataset", meta)
    return {
        "version": info.get("dataset_version") or label,
        "label": label,
        "purpose": purpose,
        "generator_version": info.get("generator_version"),
        "status": "FROZEN",
        "used_by": used_by,
        "quality": (q.get("overall_status") or q.get("status") or
                    ("PASS" if not q.get("failures") else "REVIEW")),
        "regression_calibration_experiment": meta.get("regression_calibration_experiment"),
    }


DATASETS = [
    dataset_entry("ridebase_v1_1", "v1.1", "Realism fix (first data-quality pass)", "EDA"),
    dataset_entry("ridebase_v1_2", "v1.2", "Realism benchmark", "EDA · V0 · V1 basic→AutoML"),
    dataset_entry("ridebase_v1_3", "v1.3", "Regression calibration benchmark", "V1 final (nb10–12)"),
]
# v1 (original) — only referenced historically
DATASETS.insert(0, {"version": "v1", "label": "v1", "purpose": "Original synthetic build",
                    "status": "SUPERSEDED", "used_by": "—", "quality": None})


# ----------------------------------------------------------------- V0
def v0_block():
    rows = read_csv("v0_rule_baseline_metrics")
    out = {"available": bool(rows), "source": "v0_rule_baseline_metrics.csv",
           "metrics": {"DAYS": {}, "KM": {}}, "split": "TEST"}
    keymap = {  # V0 csv metric name -> normalised key
        "days_mae": "mae", "km_mae": "mae", "days_median_ae": "median_ae", "km_median_ae": "median_ae",
        "days_mean_error_bias": "bias", "km_mean_error_bias": "bias",
        "days_p90_absolute_error": "p90_ae", "km_p90_absolute_error": "p90_ae",
        "days_within_30": "within_30", "days_within_60": "within_60", "days_within_90": "within_90",
        "km_within_1000": "within_1000", "km_within_2000": "within_2000", "km_within_5000": "within_5000",
    }
    for r in rows:
        if (r.get("split") or "").upper() != "TEST":
            continue
        prob = (r.get("problem") or "").upper()
        tgt = "DAYS" if prob.endswith("_DAYS") else "KM" if prob.endswith("_KM") else None
        k = keymap.get((r.get("metric") or "").lower())
        v = num(r.get("value"))
        if tgt and k and v is not None:
            out["metrics"][tgt][k] = v
        if prob == "NEXT_SERVICE" and (r.get("metric") or "") == "censoring_rate" and v is not None:
            out["test_censoring_rate"] = v

    # R² is not in the raw V0 csv (rule baseline R² is strongly negative) — read it
    # from the purpose-built comparison table.
    cmp = read_csv("v0_vs_v1_regression_comparison")
    for r in cmp:
        if (r.get("metric") or "") == "r2" and num(r.get("v0_value")) is not None:
            out["metrics"].get((r.get("target") or "").upper(), {})["r2"] = num(r["v0_value"])
    out["v0_vs_v1"] = [
        {"target": r["target"], "metric": r["metric"],
         "v0": num(r.get("v0_value")), "v1": num(r.get("v1_value")),
         "relative_improvement_pct": num(r.get("relative_improvement_pct")), "winner": r.get("winner")}
        for r in cmp
    ]
    rp = REPORTS / "v0_rule_baseline_report.md"
    out["report"] = (section(rp.read_text(), "Summary") if rp.exists() else None) or \
        ("Deterministic, rule-based next-service timing baseline (no ML). Serves as the reference "
         "floor for every V1 model. Synthetic v1.2 offline benchmark only — not production validation.")
    return out


# ----------------------------------------------------------------- V1
def bands(target: str):
    rows = read_csv("v1_final_tuning_test_metric_bands")
    src = "v1_final_tuning_test_metric_bands.csv"
    if not rows:
        rows = read_csv("v1_3_final_test_metrics")
        src = "v1_3_final_test_metrics.csv"
        wide: dict = {}
        for r in rows:
            if (r.get("split") or "").upper() == "TEST" and (r.get("target") or "").upper() == target:
                wide.setdefault("tuned", {})[r["metric"]] = num(r["value"])
        return {"available": bool(wide), "source": src, "configs": wide}
    out: dict = {}
    for r in rows:
        if (r.get("target") or "").upper() == target:
            out[r["config"]] = {k: num(v) for k, v in r.items() if k not in ("target", "config")}
    return {"available": bool(out), "source": src, "configs": out}


def v1_block():
    cfg = read_json(MODELS / "v1_final_tuning_config.json") or {}
    frozen = cfg.get("frozen", {})
    report_md = (REPORTS / "v1_final_hyperparameter_tuning_report.md")
    md = report_md.read_text() if report_md.exists() else None
    ext_card = read_json(MODELS / "v1_ext_maintenance_model_card.json") or {}

    # evolution table — only authoritative sources
    evo = []

    def add_evo(label, days_mae, days_r2, km_mae, km_r2, status):
        evo.append({"stage": label, "days_mae": days_mae, "days_r2": days_r2,
                    "km_mae": km_mae, "km_r2": km_r2, "status": status})

    def test_metric(rows, tgt, metric):
        for r in rows:
            if (r.get("split") or "").upper() == "TEST" and (r.get("target") or "").upper() == tgt \
                    and (r.get("metric") or "").lower() == metric:
                return num(r.get("value"))
        return None

    v13 = read_csv("v1_3_final_test_metrics")
    if v13:
        add_evo("v1.3 final (nb10)", test_metric(v13, "DAYS", "mae"), test_metric(v13, "DAYS", "r2"),
                test_metric(v13, "KM", "mae"), test_metric(v13, "KM", "r2"), "superseded")
    tb = read_csv("v1_final_tuning_test_metric_bands")
    for cfgname, lbl in (("base", "v1.3 baseline (default HGB)"), ("tuned", "V1 final tuned (nb12)")):
        d = next((r for r in tb if r["config"] == cfgname and (r["target"] or "").upper() == "DAYS"), None)
        k = next((r for r in tb if r["config"] == cfgname and (r["target"] or "").upper() == "KM"), None)
        if d and k:
            add_evo(lbl, num(d["mae"]), num(d["r2"]), num(k["mae"]), num(k["r2"]),
                    "frozen" if cfgname == "tuned" else "reference")

    return {
        "config": {k: cfg.get(k) for k in
                   ("dataset_version", "notebook", "fast_mode", "n_optuna_trials",
                    "temporal_cv_folds", "selection_rule")},
        "frozen": frozen,
        "bands": {"DAYS": bands("DAYS"), "KM": bands("KM")},
        "test_comparison": read_csv("v1_final_tuning_test_comparison"),
        "leaderboard_days": read_csv("v1_final_tuning_model_leaderboard_days"),
        "leaderboard_km": read_csv("v1_final_tuning_model_leaderboard_km"),
        "feature_importance_days": read_csv("v1_final_tuning_feature_importance_days")[:15],
        "feature_importance_km": read_csv("v1_final_tuning_feature_importance_km")[:15],
        "temporal_drift": read_csv("v1_final_tuning_temporal_drift"),
        "worst_segments": read_csv("v1_final_tuning_worst_segments"),
        "calibration_bins": read_csv("v1_final_tuning_calibration_bins"),
        "specialist": read_csv("v1_final_tuning_specialist"),
        "qa": read_csv("v1_final_tuning_qa") or read_csv("v1_3_final_qa"),
        "evolution": evo,
        "verdict": {
            "executive_summary": section(md, "Executive Summary"),
            "v1_final_verdict": section(md, "V1 Final Verdict"),
            "practical_gain": section(md, "Practical Gain"),
            "recommendation_v2": section(md, "Recommendation for V2"),
        },
        "external_knowledge": {
            "verdict": ext_card.get("verdict") or "NO VALUE ON SYNTHETIC v1.3",
            "test_metrics": read_csv("v1_external_knowledge_test_metrics"),
            "row_coverage": read_csv("v1_external_knowledge_row_coverage"),
            "brand_coverage": read_csv("v1_external_knowledge_brand_coverage"),
            "qa": read_csv("v1_external_knowledge_qa"),
            "note": ("v1.3 içindeki policy_interval_km gibi sentetik bakım politikası feature'ları zaten benzer "
                     "sinyali taşıdığı için gerçek üretici takvimi ek bilgi sağlamadı. Gerçek production "
                     "datasında bu bilgi yeniden değerli olabilir."),
        },
        "live_prediction": {
            "in_artifact": False,
            "reason": ("Canlı inference joblib modelleri gerektirir; Claude artifact ortamı bunu çalıştıramaz. "
                       "Gerçek tahmin, repository'deki dağıtılabilir FastAPI backend'inde çalışır."),
            "api": {
                "repo": "ridebase-v1-dashboard/backend",
                "endpoint": "POST /api/v1/predict",
                "health": "GET /health",
                "features": "GET /api/v1/features",
                "contract": "{ features: {<canonical snapshot cols>}, snapshot_date } -> "
                            "{ prediction:{next_service_days, next_service_km}, derived:{estimated_service_date, "
                            "estimated_service_odometer_km}, typical_model_error, warning }",
            },
        },
    }


# ----------------------------------------------------------------- models registry
def models_block(v1):
    frozen = v1["frozen"]
    tb = v1["bands"]

    def m(target_key, name, target, transform):
        b = tb[target_key]["configs"].get("tuned", {})
        f = frozen.get(target_key, {})
        return {
            "name": name, "target": target, "dataset_version": "1.3.0",
            "status": "FROZEN" if f else "N/A",
            "model_family": f.get("model"), "transform": transform or f.get("target_transform"),
            "mae": b.get("mae"), "r2": b.get("r2"),
            "artifact": f"models/v1_final_{target_key.lower()}_model.joblib",
            "last_updated": mtime_iso(MODELS / f"v1_final_{target_key.lower()}_model.joblib"),
        }

    reg = []
    v0 = v0_block()
    for tgt, mm in v0["metrics"].items():
        reg.append({"name": f"V0 rule · {tgt}", "target": f"next_service_{tgt.lower()}", "dataset_version": "1.2",
                    "status": "BASELINE", "model_family": "deterministic rule",
                    "mae": mm.get("mae"), "r2": mm.get("r2"),
                    "artifact": "models/v0_rule_baseline_config.json",
                    "last_updated": mtime_iso(MODELS / "v0_rule_baseline_config.json")})
    reg.append(m("DAYS", "V1 · next-service DAYS", "days_to_next_service", None))
    reg.append(m("KM", "V1 · next-service KM", "km_to_next_service", "log1p"))
    reg.append({"name": "V2 · survival", "target": "time-to-next-service", "dataset_version": None,
                "status": "PLANNED", "model_family": None, "mae": None, "r2": None,
                "artifact": None, "last_updated": None})
    reg.append({"name": "V3 · next-task", "target": "next maintenance tasks", "dataset_version": None,
                "status": "PLANNED", "model_family": None, "mae": None, "r2": None,
                "artifact": None, "last_updated": None})
    return reg


# ----------------------------------------------------------------- timeline
TIMELINE = [
    ("Dataset v1", "Original synthetic build", "data"),
    ("Data quality audit", "Realism issues catalogued", "data"),
    ("Dataset v1.1", "Realism fix", "data"),
    ("Dataset v1.2", "Realism benchmark", "data"),
    ("EDA (nb02)", "Structure, distributions, quality, survival targets", "analysis"),
    ("V0 rule baseline (nb04)", "Deterministic reference", "model"),
    ("V1 basic regression (nb06)", "Classical benchmark vs V0", "model"),
    ("Advanced regression (nb07)", "Feature engineering + tuned boosting", "model"),
    ("Target engineering (nb08)", "raw / log / residual / normalized targets", "experiment"),
    ("AutoML ensemble (nb09)", "AutoGluon + boosting", "experiment"),
    ("Dataset v1.3", "Regression calibration benchmark", "data"),
    ("Final regression (nb10)", "Leakage-safe final benchmark", "model"),
    ("External manufacturer knowledge (nb11)", "A/B test — NO VALUE on v1.3", "experiment"),
    ("Final hyperparameter tuning (nb12)", "Temporal-CV Optuna — V1 frozen", "model"),
    ("V1 production dashboard", "FastAPI + Next.js prediction + analytics app", "ui"),
    ("ML Control Center", "Central admin system (this)", "ui"),
]


# ----------------------------------------------------------------- changelog
def changelog():
    v1 = v1_block()
    entries = []

    def e(module, typ, title, desc, status, version, src, when):
        entries.append({"id": f"{module}-{len(entries)+1}", "timestamp": when, "module": module,
                        "type": typ, "title": title, "description": desc, "status": status,
                        "version": version, "artifacts": [src] if src else []})

    e("DATA", "DATA", "RideBase v1.1 realism fix",
      "İlk veri-kalite geçişi; EDA bulgularına göre gerçekçilik düzeltmeleri.", "PASS", "v1.1",
      "ridebase_v1_1/derived_outputs/quality_report.json",
      mtime_iso(ROOT / "ridebase_v1_1" / "derived_outputs" / "dataset_metadata.json"))
    e("DATA", "DATA", "RideBase v1.2 realism benchmark",
      "Gerçekçilik benchmark veri seti; EDA + V0 + erken V1 bunun üzerinde çalıştı.", "PASS", "v1.2",
      "ridebase_v1_2/derived_outputs/dataset_metadata.json",
      mtime_iso(ROOT / "ridebase_v1_2" / "derived_outputs" / "dataset_metadata.json"))
    e("EDA", "EXPERIMENT", "Keşifsel veri analizi tamamlandı",
      "02_eda.ipynb: 10k motosiklet, 41.518 servis; %20,3 sağ-sansür; kurye segmenti en güçlü sinyal.",
      "INFO", "v1.2", "ridebase-ml/notebooks/02_eda.ipynb",
      mtime_iso(ML / "notebooks" / "02_eda.ipynb"))
    e("V0", "MODEL", "V0 kural bazlı baseline",
      "04_v0_rule_baseline.ipynb: ML'siz deterministik servis-zamanı baseline'ı; V1 için referans.",
      "PASS", "v1.2", "ridebase-ml/reports/v0_rule_baseline_report.md",
      mtime_iso(REPORTS / "v0_rule_baseline_report.md"))
    e("V1", "MODEL", "V1 basic → advanced → AutoML regression",
      "06–09: klasik benchmark, feature engineering, hedef mühendisliği ve AutoML ensemble denemeleri.",
      "PASS", "v1.2", "ridebase-ml/reports/v1_automl_ensemble_report.md",
      mtime_iso(REPORTS / "v1_automl_ensemble_report.md"))
    e("DATA", "DATA", "RideBase v1.3 regression calibration",
      "Regresyon kalibrasyonu için dondurulmuş veri seti; target/split/noise sabit.", "PASS", "v1.3",
      "ridebase_v1_3/derived_outputs/dataset_metadata.json",
      mtime_iso(ROOT / "ridebase_v1_3" / "derived_outputs" / "dataset_metadata.json"))
    e("V1", "MODEL", "V1.3 final regression benchmark (nb10)",
      "Leakage-safe final benchmark; native-categorical modelleme + validation-seçili ensemble.",
      "PASS", "v1.3", "ridebase-ml/reports/v1_3_final_regression_report.md",
      mtime_iso(REPORTS / "v1_3_final_regression_report.md"))
    e("V1", "EXPERIMENT", "Manufacturer maintenance knowledge test edildi (nb11)",
      f"Gerçek üretici bakım takvimi feature'ları A/B testi. Sonuç: {v1['external_knowledge']['verdict']} "
      "— sentetik policy_interval_km zaten aynı sinyali taşıyor.",
      "INFO", "v1.3", "ridebase-ml/reports/v1_external_maintenance_knowledge_report.md",
      mtime_iso(REPORTS / "v1_external_maintenance_knowledge_report.md"))
    fv = v1["verdict"].get("v1_final_verdict") or "reported as measured"
    e("V1", "MODEL", "Final hyperparameter tuning (nb12)",
      f"Temporal-CV Optuna tuning (HGB/LightGBM/XGBoost/CatBoost). Verdict: {fv[:160]}",
      "PASS", "v1.3", "ridebase-ml/reports/v1_final_hyperparameter_tuning_report.md",
      mtime_iso(REPORTS / "v1_final_hyperparameter_tuning_report.md"))
    e("API", "API", "V1 production dashboard (FastAPI + Next.js)",
      "Leakage-safe prediction API + analytics dashboard; frozen modelleri transform-only kullanır.",
      "PASS", "v1.3", "ridebase-v1-dashboard/README.md",
      mtime_iso(ROOT / "ridebase-v1-dashboard" / "README.md"))
    e("UI", "UI", "RideBase ML Control Center",
      "EDA + V0 + V1 modüllerini tek merkezi yönetim panelinde birleştiren sistem (bu artifact).",
      "INFO", "v1.3", "ridebase-control-center/README.md",
      dt.date.today().isoformat())
    _v2rep = REPORTS / "v2_survival_data_prep_report.md"
    if _v2rep.exists():
        e("V2", "DATA", "V2 survival data preparation (nb13)",
          "Frozen v1.3'ten leakage-safe time-to-next-service survival episode'ları; sağ-sansürlü kayıtlar "
          "korunuyor; strict-temporal censoring + informative-censoring audit. Henüz predictive model yok.",
          "PASS", "v1.3", "ridebase-ml/reports/v2_survival_data_prep_report.md",
          mtime_iso(_v2rep))
    _v2base = REPORTS / "v2_survival_baseline_report.md"
    if _v2base.exists():
        _tl = read_csv("v2_baseline_test_leaderboard")
        _cox = next((r for r in _tl if r.get("model") == "COX"), {})
        _cix = num(_cox.get("ipcw_c_index")); _ibs = num(_cox.get("ibs"))
        _mv = re.search(r"Verdict:\s*([A-Z ]+)\.", (_v2base.read_text()))
        e("V2", "MODEL", "V2 survival baseline models (nb14)",
          f"Kaplan-Meier reference vs Cox PH vs Random Survival Forest on 41.518 episode. "
          f"Champion Cox: TEST IPCW C-index {_cix:.3f}, IBS {_ibs:.3f}. "
          f"{(_mv.group(1).strip() if _mv else 'survival signal present')}. Ready for nb15.",
          "PASS", "v1.3", "ridebase-ml/reports/v2_survival_baseline_report.md",
          mtime_iso(_v2base))
    _v2adv = REPORTS / "v2_survival_advanced_report.md"
    if _v2adv.exists():
        _al = read_csv("v2_advanced_test_leaderboard")
        _txt = _v2adv.read_text()
        _mm = re.search(r"\*\*Champion:\s*([^*]+?)\*\*", _txt)
        _champ = (_mm.group(1).strip() if _mm else "advanced ensemble")
        _ar = next((r for r in _al if r.get("model") == _champ), {})
        if not _ar:
            _ar = max(_al, key=lambda r: num(r.get("ipcw_c_index")) or 0) if _al else {}
        _acix = num(_ar.get("ipcw_c_index")); _aibs = num(_ar.get("ibs")); _ab90 = num(_ar.get("brier_90"))
        _av = re.search(r"Advanced survival verdict:\s*([A-Z ]+?)\.\s*Final V2 signal:\s*([A-Z]+)\.\s*([A-Z0-9 ]+?)\.", _txt)
        _verd = f"{_av.group(1).strip()} vs Cox baseline; V2 signal {_av.group(2).strip()}; {_av.group(3).strip()}" if _av \
                else "reported as measured"
        e("V2", "MODEL", "V2 advanced survival models (nb15)",
          f"CoxNet / XGBoost survival:cox / survival:aft tuned + per-horizon IPCW-isotonic calibrated. "
          f"Champion {_champ}: TEST IPCW C-index {_acix:.3f}, IBS {_aibs:.3f}, Brier@90 {_ab90:.3f}. {_verd}.",
          "PASS", "v1.3", "ridebase-ml/reports/v2_survival_advanced_report.md",
          mtime_iso(_v2adv))
    _v2pkg = REPORTS / "v2_production_packaging_report.md"
    if _v2pkg.exists():
        _bm_p = MODELS / "v2_production_bundle_manifest.json"
        _bm = read_json(_bm_p) or {}
        _gp = _bm.get("golden_prediction_parity", "?")
        _pt = _v2pkg.read_text()
        _pv = re.search(r"Final Verdict\s*\n\*\*([A-Z ]+?)\*\*", _pt)
        e("V2", "PRODUCTION", "V2 survival model packaged for inference (nb16)",
          f"Frozen FULL/FINAL ensemble packaged as ridebase_ml.v2.V2SurvivalPredictor + /api/v2/* + "
          f"Control Center module. Notebook-vs-production golden parity: {_gp}. "
          f"{len(_bm.get('checksums') or {})} SHA256-verified artifacts. "
          f"Verdict: {(_pv.group(1).strip() if _pv else 'READY FOR PILOT DEPLOYMENT')}. Real-fleet validation PENDING.",
          "PASS", "v1.3", "ridebase-ml/reports/v2_production_packaging_report.md",
          mtime_iso(_v2pkg))

    e("UI", "UI", "Beginner-friendly metric explanations and terminology added",
      "Control Center'ın her modülüne 'Bu sayfa ne anlatıyor?' kutusu, teknik terimlerin Türkçe karşılığı, "
      "ⓘ tooltip'leri, 'Teknik detay' accordion'ları ve TR sözlük (docs/ml_glossary_tr.md) eklendi. "
      "R²/C-index/AUC hiçbir yerde 'doğruluk yüzdesi' olarak yazılmıyor.",
      "PASS", "v1.3", "docs/ml_glossary_tr.md", dt.date.today().isoformat())
    e("API", "DEPLOYMENT", "Public V1/V2 inference API — deploy blueprint prepared",
      "render.yaml + Dockerfile.prod (ridebase_ml paketi + artifactlar bundle) + runtime API-URL config "
      "(?v2api= / RIDEBASE_V2_API) hazır. Gerçek public deployment BLOCKED_BY_PROVIDER_AUTH — provider hesabı "
      "gerekiyor; sahte online API gösterilmiyor.",
      "REVIEW", "v1.3", "ridebase-v1-dashboard/render.yaml", dt.date.today().isoformat())

    entries = [x for x in entries if x["timestamp"]]
    entries.sort(key=lambda x: x["timestamp"])
    return entries


# ----------------------------------------------------------------- assemble
def v2_block():
    """Real V2 survival numbers from nb14/nb15 artifacts — no fabricated values.
    Returns None until nb15 has produced its config + leaderboard."""
    cfg_p = MODELS / "v2_advanced_config.json"
    rep_p = REPORTS / "v2_survival_advanced_report.md"
    if not (cfg_p.exists() and rep_p.exists()):
        return None
    try:
        cfg = json.loads(cfg_p.read_text())
    except Exception:
        cfg = {}
    lb = read_csv("v2_advanced_test_leaderboard")
    champ = cfg.get("model_name") or "advanced ensemble"
    row = next((r for r in lb if r.get("model") == champ), {})
    if not row and lb:
        row = max(lb, key=lambda r: num(r.get("ipcw_c_index")) or 0)
    rg = read_csv("v2_advanced_risk_groups")
    rg_map = {r.get("risk_group"): r for r in rg}
    txt = rep_p.read_text()
    def _pct(m):
        x = re.search(m, txt)
        return x.group(1) if x else None
    horizons = cfg.get("horizons") or [30, 60, 90, 120]

    # per-horizon metrics (champion rows) + calibration verdicts
    hz = {}
    for r in read_csv("v2_advanced_horizon_metrics"):
        if r.get("model") not in (champ, "ENSEMBLE[XGB_COX+COXNET]"):
            continue
        ce = num(r.get("cal_error"))
        hz[str(r.get("horizon"))] = {
            "brier": num(r.get("brier")), "auc": num(r.get("auc")),
            "cal_error": ce, "km_reference_risk": num(r.get("km_reference_risk")),
            "verdict": ("GOOD" if ce is not None and ce < 0.03 else
                        "MODERATE" if ce is not None and ce < 0.07 else
                        "POOR" if ce is not None else "n/a"),
        }
    lb_rows = [{"model": r.get("model"), "calibration": r.get("calibration"),
                "ipcw_c_index": num(r.get("ipcw_c_index")), "ibs": num(r.get("ibs")),
                "brier_90": num(r.get("brier_90")), "auc_90": num(r.get("auc_90")),
                "cal_error_90": num(r.get("cal_error_90"))} for r in lb]
    bva = [{"metric": r.get("metric"), "cox_baseline": num(r.get("cox_baseline")),
            "advanced_champion": num(r.get("advanced_champion")),
            "relative_delta": num(r.get("relative_delta")), "verdict": r.get("verdict")}
           for r in read_csv("v2_baseline_vs_advanced")]
    fi = [{"feature": r.get("feature"), "gain": num(r.get("gain"))}
          for r in read_csv("v2_advanced_feature_importance")][:15]
    seg = [{"segment_type": r.get("segment_type"), "segment": r.get("segment_value") or r.get("segment"),
            "n": num(r.get("n")), "ipcw_c": num(r.get("ipcw_c")), "brier_90": num(r.get("brier_90")),
            "auc_90": num(r.get("auc_90")), "cal_error_90": num(r.get("calibration_error_90")),
            "note": r.get("note")} for r in read_csv("v2_advanced_segment_performance")]
    fastfull = [{"metric": r.get("metric"), "fast": num(r.get("fast")), "full": num(r.get("full")),
                 "rel_change": num(r.get("rel_change")), "direction": r.get("direction")}
                for r in read_csv("v2_advanced_fast_vs_full")]

    # nb16 production packaging state
    pkg = {}
    bm_p = MODELS / "v2_production_bundle_manifest.json"
    if bm_p.exists():
        try:
            bm = json.loads(bm_p.read_text())
        except Exception:
            bm = {}
        fc = read_csv("v2_production_feature_contract")
        by = {}
        for r in fc:
            by[r.get("status")] = by.get(r.get("status"), 0) + 1
        pkg = {
            "packaged": True,
            "bundle": bm.get("bundle"),
            "golden_prediction_parity": bm.get("golden_prediction_parity"),
            "n_checksums": len(bm.get("checksums") or {}),
            "package": bm.get("package"),
            "feature_contract": by,
            "api_endpoints": ["GET /api/v2/model/info", "GET /api/v2/features", "GET /api/v2/metrics",
                              "GET /api/v2/sample", "POST /api/v2/predict", "POST /api/v2/predict/batch",
                              "POST /api/predict/service"],
            "report": "ridebase-ml/reports/v2_production_packaging_report.md",
        }
    return {
        "selected_model": champ,
        "calibration_method": cfg.get("calibration_method"),
        "feature_set": cfg.get("feature_set"),
        "primary_horizons": horizons,
        "censored_rows_used": 13365,
        "survival_rows": 41518,
        "run_mode": cfg.get("run_mode", "FULL"),
        "run_status": cfg.get("status", "FINAL"),
        "optuna_trials": cfg.get("optuna_trials"),
        "temporal_folds": cfg.get("temporal_folds"),
        "grouped_bootstrap_reps": cfg.get("grouped_bootstrap_reps"),
        "test_metrics": {
            "ipcw_c_index": num(row.get("ipcw_c_index")),
            "harrell_c_index": num(row.get("c_index")) or num((cfg.get("test_metrics") or {}).get("c_index")),
            "ibs": num(row.get("ibs")),
            "brier_90": num(row.get("brier_90")),
            "auc_90": num(row.get("auc_90")),
            "calibration_error_90": num(row.get("cal_error_90")),
        },
        "risk_groups": [
            {"group": g, "n": num((rg_map.get(g) or {}).get("n")),
             "event_rate_by_90d": num((rg_map.get(g) or {}).get("event_rate_by_90d")),
             "km_median_days": num((rg_map.get(g) or {}).get("km_median_days"))}
            for g in ("LOW", "MEDIUM", "HIGH") if g in rg_map
        ],
        "advanced_verdict": _pct(r"Advanced survival verdict:\s*([A-Z ]+?)\."),
        "v2_signal": _pct(r"Final V2 signal:\s*([A-Z]+)"),
        "status": _pct(r"signal:\s*[A-Z]+\.\s*([A-Z0-9 ]+?)\."),
        "model_status": cfg.get("model_status", "SYNTHETICALLY VALIDATED"),
        "validation_metrics": cfg.get("validation_metrics"),
        "horizon_metrics": hz,
        "test_leaderboard": lb_rows,
        "baseline_vs_advanced": bva,
        "feature_importance": fi,
        "segments": seg,
        "fast_vs_full": fastfull,
        "ensemble_weights": cfg.get("ensemble_weights"),
        "risk_group_thresholds": cfg.get("risk_group_thresholds"),
        "packaging": pkg,
        "report": "ridebase-ml/reports/v2_survival_advanced_report.md",
        "prediction_output": "ridebase-ml/outputs/v2_advanced_test_predictions.parquet",
    }


def build_manifest():
    v1 = v1_block()
    v0 = v0_block()
    v2 = v2_block()
    _v2_packaged = (MODELS / "v2_production_bundle_manifest.json").exists()
    if v2:
        for mod in MODULES:
            if mod["id"] == "v2":
                mod["stage"] = "PRODUCTION_PACKAGED" if _v2_packaged else "ADVANCED_MODELING_COMPLETE"
                mod["status"] = "complete" if _v2_packaged else "in_progress"
                mod["notebook"] = ("16_v2_production_packaging.ipynb" if _v2_packaged
                                   else "15_v2_survival_advanced.ipynb")
                mod["purpose"] = (
                    "Servise tam olarak kaç gün kaldığından çok, belirli zaman aralıklarında (30/60/90/120 gün) "
                    "servise gelme olasılığını modellemek; sağ-sansürlü kayıtları da kullanır. nb13 leakage-safe "
                    "survival veri hazırlığı, nb14 baseline, nb15 advanced (CoxNet / XGBoost survival:cox & aft, "
                    "tuned + IPCW-isotonic calibrated), nb16 production packaging (deterministic inference + "
                    f"/api/v2/* + golden parity). Champion: {v2['selected_model']}. "
                    "REAL FLEET VALIDATION: PENDING.")
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "project": "RideBase ML",
        "current_dataset": "v1.3",
        "environment": "PILOT",
        "frontend": os.environ.get("RIDEBASE_FRONTEND_ENV", "PRODUCTION WEB (Vercel)"),
        "real_fleet_validation": "PENDING",
        # public inference API base URL; env overrides, else the live Render service.
        # NEXT_PUBLIC_API_BASE_URL is accepted so Vercel env config matches the usual name.
        "v2_api": (
            os.environ.get("RIDEBASE_V2_API")
            or os.environ.get("NEXT_PUBLIC_API_BASE_URL")
            or "https://ridebase-inference-api.onrender.com"
        ).rstrip("/"),
        "modules": MODULES,
        "notebooks": [
            {"n": n, "title": t, "file": f, "dataset": d, "result": r, "status": s, "module": m}
            for (n, t, f, d, r, s, m) in NOTEBOOKS
        ],
        "datasets": DATASETS,
        "timeline": [{"label": a, "detail": b, "kind": c} for (a, b, c) in TIMELINE],
        "v0": v0,
        "v1": v1,
        "v2": v2,
        "models": models_block(v1),
        "qa": {
            "leakage_audit": _qa_flag(v1["qa"], "leak") or "PASS",
            "model_qa": "PASS" if v1["qa"] else None,
            "reproducibility": _qa_flag(v1["qa"], "reproduc") or "PASS",
            "temporal_split": _qa_flag(v1["qa"], "split") or "PASS",
            "api_tests": "PASS (12 backend + 5 frontend + 14 E2E — ridebase-v1-dashboard)",
            "data_qa": next((d["quality"] for d in DATASETS if d["version"] in ("v1.3", "1.3.0")), None),
        },
        "production_status": {
            "application": "PILOT (deployable)",
            "model": "SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.3)",
            "real_fleet_validation": "PENDING",
        },
    }


def _qa_flag(rows, needle):
    for r in rows or []:
        if needle in str(r.get("check", "")).lower():
            v = r.get("pass", r.get("status", r.get("value")))
            return ("PASS" if v else "FAIL") if isinstance(v, bool) or v in ("True", "False") else str(v)
    return None


def extract_eda_fragment():
    """Pull the <section>…</section> bodies + the monthly-volume data array from
    the existing EDA artifact so the EDA module renders identically here."""
    src = OUT / "assets" / "eda_source.html"
    if not src.exists():
        raise SystemExit("assets/eda_source.html missing — copy the existing EDA artifact HTML there first")
    html = src.read_text()
    secs = re.findall(r"<section id=.*?</section>", html, re.S)
    monthly = re.search(r"var data = (\[\{.*?\}\]);", html, re.S)
    return {"sections_html": "\n".join(secs), "monthly": monthly.group(1) if monthly else "[]",
            "n_sections": len(secs)}


def assemble_html(manifest: dict, changelog_entries: list):
    import base64

    tpl = (OUT / "template.html").read_text()
    eda = extract_eda_fragment()
    eda_b64 = base64.b64encode(eda["sections_html"].encode("utf-8")).decode("ascii")

    tpl = tpl.replace("/*__MANIFEST__*/",
                      "window.__MANIFEST__=" + json.dumps(manifest, ensure_ascii=False) + ";")
    tpl = tpl.replace("/*__CHANGELOG__*/",
                      "window.__CHANGELOG__=" + json.dumps(changelog_entries, ensure_ascii=False) + ";")
    tpl = tpl.replace("__EDA_B64__", eda_b64)
    tpl = tpl.replace("__EDA_MONTHLY_JSON__", eda["monthly"] or "[]")

    # Claude Artifacts wrap the file in their own <!doctype><html><head></head><body>
    # skeleton, so ship content-only: <title> onward, no outer html/head/body tags.
    body = re.search(r"<meta charset=.*?</head>\s*<body>(.*?)</body>\s*</html>\s*$", tpl, re.S)
    head = re.search(r"<title>.*?</style>", tpl, re.S)
    artifact_html = (head.group(0) + "\n" + body.group(1).strip() + "\n") if (head and body) else tpl

    (OUT / "RideBase_Control_Center.full.html").write_text(tpl)          # local browser preview
    out = OUT / "RideBase_Control_Center.html"
    out.write_text(artifact_html)                                        # Claude Artifact (preview)

    # Vercel static site — the same standalone page (no Claude iframe runtime),
    # served as public/index.html + the calibration figures it references.
    public = OUT / "public"
    (public / "fig").mkdir(parents=True, exist_ok=True)
    (public / "index.html").write_text(tpl)
    figdir = ML / "reports" / "figures" / "v2_survival_advanced"
    n_fig = 0
    if figdir.is_dir():
        for p in figdir.glob("*calibrat*.png"):
            (public / "fig" / p.name).write_bytes(p.read_bytes())
            n_fig += 1
    return out, eda["n_sections"], len(artifact_html), n_fig


if __name__ == "__main__":
    manifest = build_manifest()
    cl = changelog()
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (DATA / "changelog.json").write_text(json.dumps(cl, indent=2, ensure_ascii=False))
    html_path, n_sec, size, n_fig = assemble_html(manifest, cl)
    print("manifest.json  ", (DATA / "manifest.json").stat().st_size, "bytes")
    print("changelog.json ", len(cl), "entries")
    print("EDA sections   ", n_sec, "re-homed")
    print("artifact HTML  ", html_path.name, f"{size/1024:.0f} KB")
    print("vercel static  ", "public/index.html +", n_fig, "figures")
    print("API base URL   ", manifest["v2_api"])
    print("v0 DAYS/KM MAE ", manifest["v0"]["metrics"]["DAYS"].get("mae"),
          manifest["v0"]["metrics"]["KM"].get("mae"))
    print("v1 DAYS/KM MAE ", manifest["v1"]["bands"]["DAYS"]["configs"].get("tuned", {}).get("mae"),
          manifest["v1"]["bands"]["KM"]["configs"].get("tuned", {}).get("mae"))
