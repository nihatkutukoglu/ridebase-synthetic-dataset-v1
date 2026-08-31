"""/api/v2/* — V2 survival probability service.

Serves calibrated 30/60/90/120-day service probabilities from the frozen FULL/FINAL
ensemble. Model status: SYNTHETICALLY VALIDATED (v1.3); real-fleet validation PENDING.
"""
from __future__ import annotations

import csv
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .config import settings
from .v2_schemas import UnifiedServiceRequest, V2BatchPredictRequest, V2PredictRequest
from .v2_service import V2Unavailable, get_predictor

v2 = APIRouter(prefix="/api/v2", tags=["v2"])

_SYNTH_WARNING = ("Real-fleet validation pending. This model is SYNTHETICALLY VALIDATED on "
                  "RideBase Synthetic Dataset v1.3 only — not production-validated.")


def _pred():
    try:
        return get_predictor()
    except V2Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V2 model unavailable: {exc}")


def _read_csv(name: str) -> List[Dict[str, str]]:
    p = settings.REPORTS_DIR / "tables" / f"{name}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


@v2.get("/model/info")
def model_info() -> Dict[str, Any]:
    return _pred().model_info()


@v2.get("/features")
def features() -> Dict[str, Any]:
    return _pred().features()


@v2.get("/sample")
def sample() -> Dict[str, Any]:
    p = _pred()
    return {"features": p.sample_snapshot(),
            "note": "A production-safe example built from training medians/modes. Do not send 'split'."}


@v2.get("/metrics")
def metrics() -> Dict[str, Any]:
    """Artifact-driven — nb15/nb16 tables + config. No hard-coded numbers."""
    p = _pred()
    cfg = p.cfg
    bundle_manifest = settings.MODEL_DIR / "v2_production_bundle_manifest.json"
    manifest = json.loads(bundle_manifest.read_text()) if bundle_manifest.exists() else {}
    horizon_rows = _read_csv("v2_advanced_horizon_metrics")
    champ = cfg.get("model_name")
    horizons = {}
    for r in horizon_rows:
        if r.get("model") not in (champ, "ENSEMBLE[XGB_COX+COXNET]"):
            continue
        horizons[str(r.get("horizon"))] = {
            "brier": _num(r.get("brier")), "auc": _num(r.get("auc")),
            "calibration_error": _num(r.get("cal_error")),
        }
    risk_groups = [
        {"group": r.get("risk_group"), "n": _num(r.get("n")),
         "event_rate_by_90d": _num(r.get("event_rate_by_90d")),
         "km_median_days": _num(r.get("km_median_days"))}
        for r in _read_csv("v2_advanced_risk_groups")
    ]
    boot = {r.get("metric"): {"estimate": _num(r.get("estimate")),
                              "ci_low": _num(r.get("ci_low")), "ci_high": _num(r.get("ci_high"))}
            for r in _read_csv("v2_advanced_grouped_bootstrap_ci")}
    return {
        "run_mode": cfg.get("run_mode"), "status": cfg.get("status"),
        "dataset_version": cfg.get("dataset_version"),
        "model": cfg.get("model_name"), "ensemble_weights": cfg.get("ensemble_weights"),
        "calibration_method": cfg.get("calibration_method"),
        "primary_horizons": cfg.get("horizons"),
        "survival_rows": 41518, "events": 28153, "censored_rows_used": 13365,
        "validation_metrics": cfg.get("validation_metrics"),
        "test_metrics": cfg.get("test_metrics"),
        "calibration_quality": p.calibration_quality,
        "horizon_metrics": horizons,
        "risk_groups": risk_groups,
        "grouped_bootstrap_ci": boot,
        "golden_prediction_parity": manifest.get("golden_prediction_parity"),
        "model_validation": "SYNTHETICALLY_VALIDATED",
        "real_fleet_validation": "PENDING",
    }


def _shape(result: Dict[str, Any]) -> Dict[str, Any]:
    p = result["predictions"][0]
    return {
        "prediction": {
            "risk_30d": p["risk_30d"], "risk_60d": p["risk_60d"],
            "risk_90d": p["risk_90d"], "risk_120d": p["risk_120d"],
            "median_service_days": p["median_service_days"],
            "risk_group_90d": p["risk_group_90d"],
            **({"estimated_median_service_date": p["estimated_median_service_date"]}
               if "estimated_median_service_date" in p else {}),
        },
        "model": {
            "version": result["model"]["version"],
            "family": result["model"]["family"],
            "dataset_version": result["model"]["dataset_version"],
            "run_mode": result["model"]["run_mode"],
            "status": "SYNTHETICALLY_VALIDATED",
            "real_fleet_validation": "PENDING",
        },
        "calibration": result["calibration"],
        **({"warnings": p["warnings"]} if p.get("warnings") else {}),
        "warning": _SYNTH_WARNING,
        "latency_ms": result["latency_ms"],
    }


@v2.post("/predict")
def predict(req: V2PredictRequest) -> Dict[str, Any]:
    p = _pred()
    feats = dict(req.features)
    if req.snapshot_date:
        feats["snapshot_date"] = req.snapshot_date
    try:
        result = p.predict_batch([feats], strict=req.strict)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _shape(result)


@v2.post("/predict/batch")
def predict_batch(req: V2BatchPredictRequest) -> Dict[str, Any]:
    p = _pred()
    if not req.items:
        raise HTTPException(status_code=422, detail="items must be a non-empty list")
    try:
        result = p.predict_batch(list(req.items), strict=req.strict)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    preds = []
    for pr in result["predictions"]:
        row = {k: pr[k] for k in ("risk_30d", "risk_60d", "risk_90d", "risk_120d",
                                  "median_service_days", "risk_group_90d")}
        if pr.get("warnings"):
            row["warnings"] = pr["warnings"]
        preds.append(row)
    return {
        "n": result["n"], "predictions": preds,
        "model": {"family": result["model"]["family"], "dataset_version": result["model"]["dataset_version"],
                  "status": "SYNTHETICALLY_VALIDATED", "real_fleet_validation": "PENDING"},
        "calibration": result["calibration"],
        "warning": _SYNTH_WARNING,
        "latency_ms": result["latency_ms"],
    }


# ---- optional V1 + V2 unified view -----------------------------------------------
unified = APIRouter(prefix="/api", tags=["unified"])


@unified.post("/predict/service")
def predict_service(req: UnifiedServiceRequest) -> Dict[str, Any]:
    """V1 point estimate + V2 probability-over-time for the same snapshot.
    Each model consumes only its own frozen feature contract."""
    out: Dict[str, Any] = {"warning": _SYNTH_WARNING}
    # V1
    try:
        from .artifacts import get_store
        from .predictor import predict as v1_predict
        sd = None
        if req.snapshot_date:
            import datetime as _dt
            try:
                sd = _dt.date.fromisoformat(req.snapshot_date)
            except ValueError:
                sd = None
        v1 = v1_predict(get_store(), dict(req.features), sd, strict=False)
        out["v1"] = {
            "next_service_days": v1["prediction"]["next_service_days"],
            "next_service_km": v1["prediction"]["next_service_km"],
            "estimated_service_date": v1.get("derived", {}).get("estimated_service_date"),
        }
    except Exception as exc:  # pragma: no cover
        out["v1"] = {"error": str(exc)}
    # V2
    try:
        p = get_predictor()
        feats = dict(req.features)
        if req.snapshot_date:
            feats["snapshot_date"] = req.snapshot_date
        r = p.predict_batch([feats], strict=False)["predictions"][0]
        out["v2"] = {k: r[k] for k in ("risk_30d", "risk_60d", "risk_90d", "risk_120d",
                                       "median_service_days", "risk_group_90d")}
    except V2Unavailable as exc:
        out["v2"] = {"error": f"unavailable: {exc}"}
    out["interpretation"] = ("V1 = point estimate of days/km to the next service. "
                             "V2 = calibrated probability the bike is back in the shop within each window.")
    return out
