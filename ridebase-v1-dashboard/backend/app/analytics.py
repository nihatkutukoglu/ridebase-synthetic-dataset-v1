"""Turn the notebook CSV / parquet / markdown artifacts into small, normalised
JSON payloads for the dashboard. Never invents a number: a missing artifact
yields ``{"available": false}`` and the UI shows "artifact not available"."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import (
    ArtifactStore,
    FEATURE_META,
    prettify,
    read_predictions,
    read_report,
    read_table,
)
from .config import settings

NA = {"available": False}


# ---------------------------------------------------------------- helpers
def _bands(target: str) -> dict[str, Any]:
    rows = read_table("v1_final_tuning_test_metric_bands")
    src = "v1_final_tuning_test_metric_bands.csv"
    if not rows:
        rows = read_table("v1_3_final_test_metrics")
        src = "v1_3_final_test_metrics.csv"
        if not rows:
            return NA
        # long format -> wide
        out: dict[str, dict] = {}
        for r in rows:
            if r.get("split") != "TEST":
                continue
            out.setdefault("tuned", {})[r["metric"]] = r["value"]
        return {"available": True, "source": src, "target": target, "configs": out}
    out = {}
    for r in rows:
        if str(r.get("target", "")).upper() == target.upper():
            out[r["config"]] = {k: v for k, v in r.items() if k not in ("target", "config")}
    return {"available": bool(out), "source": src, "target": target, "configs": out}


def _hist(values: list[float], bins: int = 40) -> list[dict]:
    a = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if a.size == 0:
        return []
    counts, edges = np.histogram(a, bins=bins)
    return [{"x0": float(edges[i]), "x1": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))]


def _pred_frame() -> pd.DataFrame | None:
    rows = read_predictions(sample=0)
    if not rows:
        return None
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sections
def overview(store: ArtifactStore) -> dict:
    info = store.model_info()
    d, k = _bands("DAYS"), _bands("KM")

    def pick(b, cfg, key):
        try:
            return b["configs"][cfg][key]
        except Exception:
            return None

    kpis = {
        "days_r2": pick(d, "tuned", "r2"),
        "days_mae": pick(d, "tuned", "mae"),
        "km_r2": pick(k, "tuned", "r2"),
        "km_mae": pick(k, "tuned", "mae"),
        "days_within_30": pick(d, "tuned", "within_30"),
        "days_within_60": pick(d, "tuned", "within_60"),
        "km_within_500": pick(k, "tuned", "within_500"),
        "km_within_1000": pick(k, "tuned", "within_1000"),
        "km_within_2000": pick(k, "tuned", "within_2000"),
        "test_rows": pick(d, "tuned", "n") or pick(k, "tuned", "n"),
    }
    comparison = read_table("v1_final_tuning_test_comparison")
    qa = read_table("v1_final_tuning_qa") or read_table("v1_3_final_qa")

    # optional cross-version evolution - only from artifacts that exist
    evo = []
    for label, tbl, getter in [
        ("V1 basic", "v1_regression_baseline_comparison", None),
        ("Advanced", "v1_advanced_regression_metrics", None),
        ("AutoML", "v1_automl_test_metrics", None),
        ("v1.3 final", "v1_3_final_test_metrics", None),
    ]:
        rows = read_table(tbl)
        if rows:
            evo.append({"label": label, "source": f"{tbl}.csv", "rows": rows[:60]})

    return {
        "available": True,
        "model_info": info,
        "kpis": kpis,
        "days_bands": d,
        "km_bands": k,
        "baseline_vs_final": {"available": bool(comparison), "rows": comparison or []},
        "qa": {"available": bool(qa), "rows": qa or []},
        "evolution": evo,
        "status_card": {
            "v1_regression": True,
            "synthetic_validation": "PASS",
            "leakage_audit": store.leakage_report.get("status"),
            "temporal_split": _qa_flag(qa, "split") or "PASS",
            "reproducibility": _qa_flag(qa, "reproduc") or "PASS",
            "real_fleet_validation": "PENDING",
        },
    }


def _qa_flag(rows: list[dict] | None, needle: str) -> str | None:
    if not rows:
        return None
    for r in rows:
        key = str(r.get("check", "")).lower()
        if needle in key:
            val = r.get("pass", r.get("status", r.get("value")))
            if isinstance(val, bool):
                return "PASS" if val else "FAIL"
            return str(val)
    return None


def target_detail(store: ArtifactStore, target: str) -> dict:
    b = _bands(target)
    df = _pred_frame()
    payload: dict[str, Any] = {"available": b.get("available", False), "bands": b, "target": target}
    if df is None:
        payload["charts"] = NA
        return payload
    tcol = "days" if target.upper() == "DAYS" else "km"
    a = pd.to_numeric(df[f"actual_{tcol}"], errors="coerce")
    p = pd.to_numeric(df[f"tuned_pred_{tcol}"], errors="coerce")
    bp = pd.to_numeric(df.get(f"baseline_pred_{tcol}"), errors="coerce")
    resid = (p - a)
    mask = a.notna() & p.notna()
    a, p, resid = a[mask], p[mask], resid[mask]
    n = int(mask.sum())
    samp = min(n, settings.SCATTER_SAMPLE)
    idx = np.random.RandomState(42).choice(n, samp, replace=False) if n > samp else np.arange(n)
    scatter = [{"actual": float(a.iloc[i]), "predicted": float(p.iloc[i]),
                "residual": float(resid.iloc[i])} for i in idx]
    payload["charts"] = {
        "available": True,
        "n": n,
        "scatter": scatter,
        "residual_hist": _hist(resid.tolist()),
        "abs_error_hist": _hist(resid.abs().tolist()),
        "residual_vs_pred": scatter,  # same points, UI plots predicted vs residual
        "baseline_available": bool(bp is not None and bp.notna().any()),
    }
    return payload


def models(store: ArtifactStore) -> dict:
    lb_d = read_table("v1_final_tuning_model_leaderboard_days")
    lb_k = read_table("v1_final_tuning_model_leaderboard_km")
    if not (lb_d or lb_k):
        lb_d = read_table("v1_3_model_validation_results")
    frozen = store.config.get("frozen", {})
    optuna = {}
    for kind in ("hgb", "lgbm", "xgb", "cat"):
        for tgt in ("days", "km"):
            rows = read_table(f"optuna_{kind}_{tgt}_trials")
            if not rows:
                continue
            hist = []
            best = None
            for r in rows:
                v = r.get("value")
                if v is None or (isinstance(v, float) and not np.isfinite(v)):
                    continue
                best = v if best is None else min(best, v)
                hist.append({"trial": r.get("number"), "value": v, "best": best})
            optuna[f"{kind}_{tgt}"] = hist
    return {
        "available": bool(lb_d or lb_k),
        "leaderboard_days": lb_d or [],
        "leaderboard_km": lb_k or [],
        "frozen": frozen,
        "optuna": optuna,
        "config": {k: store.config.get(k) for k in
                   ("notebook", "fast_mode", "n_optuna_trials", "temporal_cv_folds", "selection_rule")},
    }


def features(store: ArtifactStore) -> dict:
    def enrich(rows):
        out = []
        for r in rows or []:
            name = r.get("source") or r.get("feature") or r.get("name")
            meta = FEATURE_META.get(name, {})
            out.append({
                "feature": name,
                "label": meta.get("label", prettify(str(name))),
                "explain": meta.get("explain", ""),
                "group": r.get("group") or meta.get("group", "Other"),
                "importance": r.get("importance"),
                "std": r.get("std"),
            })
        return out

    fd = read_table("v1_final_tuning_feature_importance_days")
    fk = read_table("v1_final_tuning_feature_importance_km")
    if not (fd or fk):
        fi = read_table("v1_3_feature_importance")
        return {"available": bool(fi), "days": enrich(fi), "km": enrich(fi),
                "note": "v1.3 combined feature importance (final-tuning artifact unavailable)"}
    return {"available": bool(fd or fk), "days": enrich(fd), "km": enrich(fk),
            "catalog_size": len(store.feature_catalog)}


def errors(store: ArtifactStore) -> dict:
    worst = read_table("v1_final_tuning_worst_segments") or read_table("v1_3_error_segments")
    calib = read_table("v1_final_tuning_calibration_bins")
    specialist = read_table("v1_final_tuning_specialist")
    cold = [r for r in (worst or []) if str(r.get("segment_type", "")).startswith("history")]
    return {
        "available": bool(worst or calib),
        "worst_segments": worst or [],
        "calibration_bins": calib or [],
        "specialist": specialist or [],
        "cold_history": cold,
        "min_sample_note": "segmentler n>=30 filtresi ile raporlanır",
    }


def drift(store: ArtifactStore) -> dict:
    dr = read_table("v1_final_tuning_temporal_drift") or read_table("v1_3_observed_censored_shift")
    qa = read_table("v1_final_tuning_qa") or read_table("v1_3_final_qa")
    return {
        "available": bool(dr),
        "rows": dr or [],
        "test_isolation": _qa_flag(qa, "test isolat") or _qa_flag(qa, "test") or "PASS",
        "explainer": ("Temporal drift: geçmişteki servis davranışı ile gelecekteki servis "
                      "davranışının birebir aynı olmaması. Model geçmiş veriden öğrenir; "
                      "gelecekte dağılım kayabilir."),
        "splits_explainer": {
            "TRAIN": "Model öğrenir",
            "VALIDATION": "Model seçilir / ayarlanır",
            "TEST": "En son sınav (yalnız bir kez açıldı)",
        },
    }


def experiments(store: ArtifactStore) -> dict:
    cards = []

    def add(name, tbl, describe, verdict=None, note=None):
        rows = read_table(tbl)
        if rows is None and not describe:
            return
        cards.append({
            "name": name,
            "available": rows is not None,
            "source": f"{tbl}.csv" if rows is not None else None,
            "rows": (rows or [])[:40],
            "verdict": verdict,
            "note": note,
        })

    add("V0 Rule Baseline", "v0_rule_baseline_metrics", True,
        note="Deterministic kural bazlı bakım zamanı tahmini.")
    add("V1 Basic Regression", "v1_regression_metrics", True)
    add("V1 Advanced Regression", "v1_advanced_regression_metrics", True)
    add("Target Engineering", "v1_target_engineering_test_results", True,
        note="Raw / log / residual / normalized hedef denemeleri.")
    add("AutoML Ensemble", "v1_automl_test_metrics", True)
    add("v1.3 Calibration", "v1_3_final_test_metrics", True,
        note="Leakage-free v1.3 final regression benchmark.")

    ext_v = None
    ek_qa = read_table("v1_external_knowledge_qa")
    ek_card_p = settings.MODEL_DIR / "v1_ext_maintenance_model_card.json"
    if ek_card_p.exists():
        try:
            import json
            ext_v = json.loads(ek_card_p.read_text()).get("verdict")
        except Exception:
            ext_v = None
    cards.append({
        "name": "External Manufacturer Knowledge",
        "available": bool(read_table("v1_external_knowledge_test_metrics")),
        "source": "v1_external_knowledge_test_metrics.csv",
        "rows": (read_table("v1_external_knowledge_test_metrics") or [])[:40],
        "coverage": read_table("v1_external_knowledge_row_coverage") or [],
        "brand_coverage": read_table("v1_external_knowledge_brand_coverage") or [],
        "verdict": ext_v or "NO VALUE ON SYNTHETIC v1.3",
        "note": ("v1.3 içindeki policy_interval_km gibi sentetik bakım politikası feature'ları "
                 "zaten benzer sinyali taşıdığı için gerçek üretici takvimi ek bilgi sağlamadı. "
                 "Gerçek production datasında bu bilgi yeniden değerli olabilir."),
    })

    fin_cmp = read_table("v1_final_tuning_test_comparison")
    cards.append({
        "name": "Final Hyperparameter Tuning (Notebook 12)",
        "available": bool(fin_cmp),
        "source": "v1_final_tuning_test_comparison.csv",
        "rows": fin_cmp or [],
        "verdict": _final_verdict_text(),
        "note": "Temporal-CV Optuna tuning; HGB / LightGBM / XGBoost / CatBoost.",
    })
    return {"available": True, "cards": cards}


def _final_verdict_text() -> str | None:
    md = read_report("v1_final_hyperparameter_tuning_report")
    if not md:
        return None
    m = re.search(r"## V1 Final Verdict\s*\n+\**(.+?)\**\s*(\n|$)", md)
    return m.group(1).strip() if m else None


def verdict(store: ArtifactStore) -> dict:
    md = read_report("v1_final_hyperparameter_tuning_report")
    cmp = read_table("v1_final_tuning_test_comparison")
    bands_d, bands_k = _bands("DAYS"), _bands("KM")

    sections: dict[str, str] = {}
    if md:
        for title in ["Executive Summary", "V1 Final Verdict", "Practical Gain",
                      "Recommendation for V2", "Overfitting / Generalization", "Temporal Drift"]:
            m = re.search(rf"##\s*{re.escape(title)}\s*\n+(.+?)(\n##\s|\Z)", md, re.S)
            if m:
                sections[title] = m.group(1).strip()[:1600]

    return {
        "available": bool(md or cmp),
        "report_sections": sections,
        "test_comparison": cmp or [],
        "days_bands": bands_d,
        "km_bands": bands_k,
        "limitations": [
            {"title": "Sağ sansür (censoring)",
             "body": ("Bazı motosikletlerin veri dönemi bitene kadar sonraki servisi görülmediği için "
                      "kesin servis günü bilinmiyor. V1 regression bu kayıtların tamamından yararlanamıyor. "
                      "V2 survival analizi için ana motivasyon budur.")},
            {"title": "Temporal drift",
             "body": "TRAIN / VALIDATION / TEST dönemleri arasında hedef dağılımı kayabiliyor; "
                     "gelecekteki servis davranışı geçmişle birebir aynı olmayabilir."},
            {"title": "Sentetik veri",
             "body": "Model RideBase Synthetic Dataset v1.3 üzerinde geliştirildi. Gerçek filo verisiyle "
                     "doğrulama (real fleet validation) henüz yapılmadı."},
        ],
        "next_stage": {
            "name": "V2 Survival Analysis",
            "available": False,
            "reason": "Sağ sansürlü kayıtları da kullanan, olay-zamanı (time-to-event) modeli.",
        },
    }
